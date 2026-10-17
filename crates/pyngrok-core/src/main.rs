//! Bounded, authenticated reverse TCP transport. See docs/protocol.md.
use std::{
    collections::HashMap,
    io::{BufReader, Write},
    net::{IpAddr, SocketAddr},
    path::PathBuf,
    sync::{atomic::{AtomicBool, Ordering}, Arc, Mutex},
    time::Duration,
};

use anyhow::{anyhow, bail, Context, Result};
use clap::{Args, Parser, Subcommand};
use rand::{rngs::OsRng, RngCore};
use rustls::{pki_types::ServerName, ClientConfig, RootCertStore, ServerConfig};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::{lookup_host, TcpListener, TcpStream},
    sync::{mpsc, oneshot, Semaphore},
    task::{JoinHandle, JoinSet},
    time::{interval, timeout},
};
use tokio_rustls::{TlsAcceptor, TlsConnector};

const VERSION: u8 = 1;
const FRAME_LIMIT: usize = 4096;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);
const TICKET_TIMEOUT: Duration = Duration::from_secs(15);
const IDLE_TIMEOUT: Duration = Duration::from_secs(30);

trait Transport: AsyncRead + AsyncWrite + Unpin + Send {}
impl<T: AsyncRead + AsyncWrite + Unpin + Send> Transport for T {}
type Stream = Box<dyn Transport>;
type PendingMap = Arc<Mutex<HashMap<String, Pending>>>;

/// Tokio join handles otherwise detach their tasks when the owning future drops.
struct AbortOnDrop<T>(JoinHandle<T>);

impl<T> Drop for AbortOnDrop<T> {
    fn drop(&mut self) {
        self.0.abort();
    }
}

fn pending_lock(pending: &PendingMap) -> std::sync::MutexGuard<'_, HashMap<String, Pending>> {
    pending.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
}

/// Synchronous cleanup also runs when the relay cancels a session future.
struct SessionGuard {
    pending: PendingMap,
    session: String,
    active: Arc<AtomicBool>,
}

impl Drop for SessionGuard {
    fn drop(&mut self) {
        let mut pending = pending_lock(&self.pending);
        self.active.store(false, Ordering::Release);
        pending.retain(|_, ticket| ticket.session != self.session);
    }
}

#[derive(Parser)]
#[command(version, about = "High-performance pyngrok TCP transport")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Run a relay reachable by tunnel agents.
    Relay(RelayArgs),
    /// Connect a local TCP service to a relay.
    Connect(ConnectArgs),
}

#[derive(Args)]
struct RelayArgs {
    #[arg(long, default_value = "127.0.0.1:7443")]
    bind: SocketAddr,
    #[arg(long, default_value = "127.0.0.1")]
    public_bind: IpAddr,
    #[arg(long, default_value = "127.0.0.1")]
    public_host: String,
    #[arg(long, requires = "tls_key")]
    tls_cert: Option<PathBuf>,
    #[arg(long, requires = "tls_cert")]
    tls_key: Option<PathBuf>,
    #[arg(long)]
    allow_insecure: bool,
    #[arg(long, default_value = "256", value_parser = clap::value_parser!(u16).range(1..=4096))]
    max_connections: u16,
}

#[derive(Args)]
struct ConnectArgs {
    #[arg(long, default_value = "127.0.0.1:7443")]
    relay: String,
    #[arg(long)]
    upstream: String,
    #[arg(long, default_value = "0")]
    public_port: u16,
    /// Enable TLS with this certificate DNS name (or IP address).
    #[arg(long)]
    tls_server_name: Option<String>,
    #[arg(long, requires = "tls_server_name")]
    ca_cert: Option<PathBuf>,
    #[arg(long)]
    allow_insecure: bool,
    #[arg(long, default_value = "256", value_parser = clap::value_parser!(u16).range(1..=4096))]
    max_connections: u16,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum Message {
    Register { version: u8, token: String, public_port: u16 },
    Data { version: u8, token: String, ticket: String },
    Ready { version: u8, session_id: String, public_address: String },
    Incoming { version: u8, ticket: String },
    DataReady { version: u8 },
    Ping { version: u8 },
    Pong { version: u8 },
    Error { version: u8, message: String },
}

struct Pending {
    session: String,
    sender: oneshot::Sender<Stream>,
}

struct RelayState {
    token_hash: [u8; 32],
    pending: PendingMap,
    connections: Arc<Semaphore>,
    public_bind: IpAddr,
    public_host: String,
}

#[derive(Clone)]
struct Dialer {
    addresses: Arc<Vec<SocketAddr>>,
    tls: Option<(TlsConnector, ServerName<'static>)>,
}

fn emit(value: serde_json::Value) {
    // A closed stdout pipe must not crash transport tasks.
    let _ = writeln!(std::io::stdout().lock(), "{value}");
}

fn random_id() -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let mut encoded = String::with_capacity(64);
    for byte in bytes {
        encoded.push(char::from(HEX[usize::from(byte >> 4)]));
        encoded.push(char::from(HEX[usize::from(byte & 15)]));
    }
    encoded
}

fn token_hash(token: &str) -> [u8; 32] {
    Sha256::digest(token.as_bytes()).into()
}

fn authenticate(expected: &[u8; 32], candidate: &str) -> bool {
    bool::from(expected.ct_eq(&token_hash(candidate)))
}

async fn read_frame<R: AsyncRead + Unpin + ?Sized>(reader: &mut R) -> Result<Message> {
    let mut frame = Vec::with_capacity(256);
    loop {
        let byte = reader.read_u8().await.context("control connection closed")?;
        if byte == b'\n' {
            return serde_json::from_slice(&frame).context("invalid protocol frame");
        }
        if frame.len() == FRAME_LIMIT {
            bail!("protocol frame exceeds {FRAME_LIMIT} bytes");
        }
        frame.push(byte);
    }
}

async fn write_frame<W: AsyncWrite + Unpin + ?Sized>(writer: &mut W, message: &Message) -> Result<()> {
    let mut frame = serde_json::to_vec(message)?;
    if frame.len() > FRAME_LIMIT {
        bail!("outgoing protocol frame too large");
    }
    frame.push(b'\n');
    timeout(HANDSHAKE_TIMEOUT, writer.write_all(&frame))
        .await.context("control write timed out")??;
    Ok(())
}

fn tls_acceptor(cert: &PathBuf, key: &PathBuf) -> Result<TlsAcceptor> {
    let mut cert_reader = BufReader::new(std::fs::File::open(cert).context("open TLS certificate")?);
    let certs = rustls_pemfile::certs(&mut cert_reader).collect::<std::io::Result<Vec<_>>>()?;
    let mut key_reader = BufReader::new(std::fs::File::open(key).context("open TLS private key")?);
    let key = rustls_pemfile::private_key(&mut key_reader)?.context("no private key in PEM")?;
    let config = ServerConfig::builder().with_no_client_auth().with_single_cert(certs, key)?;
    Ok(TlsAcceptor::from(Arc::new(config)))
}

impl Dialer {
    async fn new(args: &ConnectArgs) -> Result<Self> {
        let addresses: Vec<_> = timeout(HANDSHAKE_TIMEOUT, lookup_host(&args.relay))
            .await.context("relay DNS lookup timed out")??.collect();
        if addresses.is_empty() {
            bail!("relay hostname resolved to no addresses");
        }
        if args.tls_server_name.is_none() && !args.allow_insecure
            && addresses.iter().any(|a| !a.ip().is_loopback())
        {
            bail!("non-loopback relay requires TLS (--tls-server-name) or explicit --allow-insecure");
        }
        let tls = if let Some(name) = &args.tls_server_name {
            let mut roots = RootCertStore::empty();
            if let Some(path) = &args.ca_cert {
                let mut reader = BufReader::new(std::fs::File::open(path).context("open CA certificate")?);
                for certificate in rustls_pemfile::certs(&mut reader) {
                    roots.add(certificate?)?;
                }
                if roots.is_empty() { bail!("CA file contains no certificates"); }
            } else {
                roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
            }
            let config = ClientConfig::builder().with_root_certificates(roots).with_no_client_auth();
            Some((TlsConnector::from(Arc::new(config)), ServerName::try_from(name.clone())?))
        } else { None };
        Ok(Self { addresses: Arc::new(addresses), tls })
    }

    async fn connect(&self) -> Result<Stream> {
        timeout(HANDSHAKE_TIMEOUT, async {
            let socket = TcpStream::connect(self.addresses.as_slice()).await?;
            socket.set_nodelay(true)?;
            let stream: Stream = match &self.tls {
                Some((connector, name)) => Box::new(connector.connect(name.clone(), socket).await?),
                None => Box::new(socket),
            };
            Ok(stream)
        }).await.context("relay connection timed out")?
    }
}

async fn handle_relay_connection(mut stream: Stream, state: Arc<RelayState>) -> Result<()> {
    let message = timeout(HANDSHAKE_TIMEOUT, read_frame(&mut *stream))
        .await.context("authentication timed out")??;
    match message {
        Message::Register { version: VERSION, token, public_port } if authenticate(&state.token_hash, &token) => {
            relay_session(stream, state, public_port).await
        }
        Message::Data { version: VERSION, token, ticket } if authenticate(&state.token_hash, &token) => {
            let pending = pending_lock(&state.pending).remove(&ticket);
            if let Some(pending) = pending {
                write_frame(&mut *stream, &Message::DataReady { version: VERSION }).await?;
                pending.sender.send(stream).map_err(|_| anyhow!("ticket expired"))?;
                Ok(())
            } else {
                bail!("invalid or expired data ticket");
            }
        }
        _ => {
            let _ = write_frame(&mut *stream, &Message::Error {
                version: VERSION, message: "authentication or protocol version rejected".into(),
            }).await;
            bail!("authentication or protocol version rejected");
        }
    }
}

async fn relay_session(mut control: Stream, state: Arc<RelayState>, port: u16) -> Result<()> {
    let listener = match TcpListener::bind(SocketAddr::new(state.public_bind, port)).await {
        Ok(listener) => listener,
        Err(_) => {
            write_frame(&mut *control, &Message::Error {
                version: VERSION, message: "public listen port unavailable".into(),
            }).await?;
            bail!("public listen port unavailable");
        }
    };
    let session = random_id();
    let active = Arc::new(AtomicBool::new(true));
    let _session_guard = SessionGuard {
        pending: state.pending.clone(), session: session.clone(), active: active.clone(),
    };
    let host = if state.public_host.contains(':') && !state.public_host.starts_with('[') {
        format!("[{}]", state.public_host)
    } else { state.public_host.clone() };
    write_frame(&mut *control, &Message::Ready {
        version: VERSION,
        session_id: session.clone(),
        public_address: format!("{host}:{}", listener.local_addr()?.port()),
    }).await?;
    let (mut reader, mut writer) = tokio::io::split(control);
    let (sender, mut receiver) = mpsc::channel::<Message>(128);
    let mut tasks = JoinSet::new();
    // One persistent read future: cancelling frame reads on incoming connections
    // would discard a partially received heartbeat frame.
    let reader_task = AbortOnDrop(tokio::spawn(async move {
        loop {
            let frame = timeout(IDLE_TIMEOUT, read_frame(&mut reader)).await??;
            match frame {
                Message::Ping { version: VERSION } => {
                    sender.send(Message::Pong { version: VERSION }).await
                        .map_err(|_| anyhow!("control writer stopped"))?;
                }
                _ => bail!("unexpected control message"),
            }
        }
        #[allow(unreachable_code)]
        Ok::<(), anyhow::Error>(())
    }));
    // Separate channel for incoming requests; control reader owns its pong sender.
    let (incoming_sender, mut incoming_receiver) = mpsc::channel::<Message>(128);
    let mut reader_task = reader_task;
    let result: Result<()> = async {
        loop {
            tokio::select! {
                result = &mut reader_task.0 => { result??; break; }
                frame = receiver.recv() => {
                    match frame {
                        Some(frame) => write_frame(&mut writer, &frame).await?,
                        None => break,
                    }
                }
                frame = incoming_receiver.recv() => {
                    if let Some(frame) = frame { write_frame(&mut writer, &frame).await?; }
                }
                accepted = listener.accept() => {
                    let (mut public, _) = accepted?;
                    let Ok(permit) = state.connections.clone().try_acquire_owned() else { continue };
                    public.set_nodelay(true)?;
                    let state = state.clone();
                    let session = session.clone();
                    let active = active.clone();
                    let sender = incoming_sender.clone();
                    tasks.spawn(async move {
                        let _permit = permit;
                        let ticket = random_id();
                        let (deliver, receive) = oneshot::channel();
                        {
                            let mut pending = pending_lock(&state.pending);
                            if !active.load(Ordering::Acquire) { return; }
                            pending.insert(ticket.clone(), Pending { session, sender: deliver });
                        }
                        let sent = sender.try_send(Message::Incoming { version: VERSION, ticket: ticket.clone() });
                        if sent.is_ok() {
                            if let Ok(Ok(mut data)) = timeout(TICKET_TIMEOUT, receive).await {
                                let _ = tokio::io::copy_bidirectional(&mut public, &mut data).await;
                            }
                        }
                        pending_lock(&state.pending).remove(&ticket);
                    });
                }
                _ = tasks.join_next(), if !tasks.is_empty() => {}
            }
        }
        Ok(())
    }.await;
    reader_task.0.abort();
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    result
}

async fn relay(args: RelayArgs, token: String) -> Result<()> {
    let tls = match (&args.tls_cert, &args.tls_key) {
        (Some(cert), Some(key)) => Some(tls_acceptor(cert, key)?),
        _ => None,
    };
    if tls.is_none() && !args.allow_insecure && !args.bind.ip().is_loopback() {
        bail!("non-loopback relay bind requires TLS or explicit --allow-insecure");
    }
    let listener = TcpListener::bind(args.bind).await.context("bind relay listener")?;
    emit(json!({"event": "relay_ready", "bind": listener.local_addr()?.to_string(),
        "public_bind": args.public_bind.to_string(), "tls": tls.is_some()}));
    let state = Arc::new(RelayState {
        token_hash: token_hash(&token), pending: Arc::new(Mutex::new(HashMap::new())),
        connections: Arc::new(Semaphore::new(args.max_connections.into())),
        public_bind: args.public_bind, public_host: args.public_host,
    });
    // Handshake/control sockets have their own budget so public sockets cannot
    // consume all capacity required by the matching data connections.
    let control_slots = Arc::new(Semaphore::new(usize::from(args.max_connections) * 2));
    let mut tasks = JoinSet::new();
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => break,
            accepted = listener.accept() => {
                let (socket, _) = accepted?;
                let Ok(permit) = control_slots.clone().try_acquire_owned() else { continue };
                socket.set_nodelay(true)?;
                let tls = tls.clone();
                let state = state.clone();
                tasks.spawn(async move {
                    let _permit = permit;
                    let stream: Result<Stream> = match tls {
                        Some(acceptor) => match timeout(HANDSHAKE_TIMEOUT, acceptor.accept(socket)).await {
                            Ok(Ok(stream)) => Ok(Box::new(stream)),
                            Ok(Err(error)) => Err(error.into()),
                            Err(error) => Err(error.into()),
                        },
                        None => Ok(Box::new(socket)),
                    };
                    if let Ok(stream) = stream {
                        if let Err(error) = handle_relay_connection(stream, state).await {
                            eprintln!("relay connection: {error}");
                        }
                    }
                });
            }
            _ = tasks.join_next(), if !tasks.is_empty() => {}
        }
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    emit(json!({"event": "stopped"}));
    Ok(())
}

async fn forward_connection(dialer: Dialer, token: Arc<String>, ticket: String, upstream: String) -> Result<()> {
    let mut local = timeout(HANDSHAKE_TIMEOUT, TcpStream::connect(&upstream))
        .await.context("upstream connection timed out")?.context("connect upstream")?;
    local.set_nodelay(true)?;
    let mut data = dialer.connect().await?;
    write_frame(&mut *data, &Message::Data { version: VERSION, token: (*token).clone(), ticket }).await?;
    match timeout(HANDSHAKE_TIMEOUT, read_frame(&mut *data)).await?? {
        Message::DataReady { version: VERSION } => {},
        _ => bail!("relay rejected data connection"),
    }
    let connection_id = random_id();
    emit(json!({"event": "connection_open", "connection_id": connection_id}));
    let result = tokio::io::copy_bidirectional(&mut local, &mut data).await;
    match result {
        Ok((bytes_up, bytes_down)) => {
            emit(json!({"event": "connection_close", "connection_id": connection_id,
                "bytes_up": bytes_up, "bytes_down": bytes_down}));
            Ok(())
        }
        Err(error) => {
            // copy_bidirectional does not return partial counters on failure.
            emit(json!({"event": "connection_close", "connection_id": connection_id,
                "bytes_up": 0, "bytes_down": 0, "counters_complete": false,
                "message": error.to_string()}));
            Err(error.into())
        }
    }
}

async fn connect(args: ConnectArgs, token: String) -> Result<()> {
    let dialer = Dialer::new(&args).await?;
    let mut control = dialer.connect().await?;
    write_frame(&mut *control, &Message::Register {
        version: VERSION, token: token.clone(), public_port: args.public_port,
    }).await?;
    match timeout(HANDSHAKE_TIMEOUT, read_frame(&mut *control)).await?? {
        Message::Ready { version: VERSION, session_id, public_address } => {
            emit(json!({"event": "tunnel_ready", "session_id": session_id,
                "public_address": public_address, "upstream": args.upstream}));
        }
        Message::Error { message, .. } => bail!("relay: {message}"),
        _ => bail!("unexpected relay registration response"),
    }
    let (mut reader, mut writer) = tokio::io::split(control);
    let (sender, mut receiver) = mpsc::channel(128);
    let mut read_task = AbortOnDrop(tokio::spawn(async move {
        loop {
            let frame = timeout(IDLE_TIMEOUT, read_frame(&mut reader)).await??;
            sender.send(frame).await.map_err(|_| anyhow!("agent stopped"))?;
        }
        #[allow(unreachable_code)]
        Ok::<(), anyhow::Error>(())
    }));
    let token = Arc::new(token);
    let slots = Arc::new(Semaphore::new(args.max_connections.into()));
    let mut heartbeat = interval(Duration::from_secs(10));
    heartbeat.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let mut tasks = JoinSet::new();
    let result: Result<()> = async {
        loop {
            tokio::select! {
                _ = tokio::signal::ctrl_c() => break,
                result = &mut read_task.0 => { result??; break; }
                _ = heartbeat.tick() => write_frame(&mut writer, &Message::Ping { version: VERSION }).await?,
                frame = receiver.recv() => {
                    match frame {
                        Some(Message::Incoming { version: VERSION, ticket }) => {
                            let Ok(permit) = slots.clone().try_acquire_owned() else {
                                eprintln!("connection limit reached; dropping public connection");
                                continue;
                            };
                            let dialer = dialer.clone();
                            let token = token.clone();
                            let upstream = args.upstream.clone();
                            tasks.spawn(async move {
                                let _permit = permit;
                                if let Err(error) = forward_connection(dialer, token, ticket, upstream).await {
                                    emit(json!({"event": "connection_error", "message": error.to_string()}));
                                }
                            });
                        }
                        Some(Message::Pong { version: VERSION }) => {},
                        Some(Message::Error { message, .. }) => bail!("relay: {message}"),
                        None => break,
                        _ => bail!("unexpected relay control message"),
                    }
                }
                _ = tasks.join_next(), if !tasks.is_empty() => {}
            }
        }
        Ok(())
    }.await;
    read_task.0.abort();
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    result?;
    emit(json!({"event": "stopped"}));
    Ok(())
}

#[tokio::main]
async fn main() -> std::process::ExitCode {
    let cli = Cli::parse();
    let result = async {
        let token = std::env::var("PYNGROK_TOKEN").context("set PYNGROK_TOKEN (at least 16 bytes)")?;
        if token.len() < 16 || token.len() > 1024 {
            bail!("PYNGROK_TOKEN must contain 16 to 1024 bytes");
        }
        match cli.command {
            Command::Relay(args) => relay(args, token).await,
            Command::Connect(args) => connect(args, token).await,
        }
    }.await;
    match result {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            emit(json!({"event": "error", "message": format!("{error:#}")}));
            eprintln!("pyngrok-core: {error:#}");
            std::process::ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authentication_rejects_wrong_and_different_length_tokens() {
        let expected = token_hash("a sufficiently long token");
        assert!(authenticate(&expected, "a sufficiently long token"));
        assert!(!authenticate(&expected, "a sufficiently long tokeN"));
        assert!(!authenticate(&expected, ""));
    }

    #[test]
    fn tickets_have_256_bits_and_unique_values() {
        let first = random_id();
        assert_eq!(first.len(), 64);
        assert!(first.bytes().all(|b| b.is_ascii_hexdigit()));
        assert_ne!(first, random_id());
    }

    #[tokio::test]
    async fn framing_preserves_application_bytes_after_newline() {
        let mut bytes = &b"{\"type\":\"data_ready\",\"version\":1}\nGET / HTTP/1.1\r\n"[..];
        assert!(matches!(read_frame(&mut bytes).await.unwrap(), Message::DataReady { version: VERSION }));
        assert_eq!(bytes, b"GET / HTTP/1.1\r\n");
    }

    #[tokio::test]
    async fn rejects_oversized_and_truncated_frames() {
        let input = vec![b'x'; FRAME_LIMIT + 1];
        assert!(read_frame(&mut input.as_slice()).await.unwrap_err().to_string().contains("exceeds"));
        assert!(read_frame(&mut &b"{\"type\":"[..]).await.is_err());
    }

    #[tokio::test]
    async fn rejects_unknown_fields_and_bad_json() {
        for input in [b"{\"type\":\"ping\",\"version\":1,\"extra\":true}\n".as_slice(), b"invalid\n"] {
            assert!(read_frame(&mut &input[..]).await.is_err());
        }
    }

    #[tokio::test]
    async fn frames_round_trip() {
        let mut frame = Vec::new();
        write_frame(&mut frame, &Message::Incoming { version: VERSION, ticket: "abc".into() }).await.unwrap();
        assert!(matches!(read_frame(&mut frame.as_slice()).await.unwrap(),
            Message::Incoming { version: VERSION, ticket } if ticket == "abc"));
    }

    #[tokio::test]
    async fn data_tickets_require_authentication_and_are_consumed_once() {
        let token = "a sufficiently long token";
        let (deliver, mut receive) = oneshot::channel();
        let pending = Arc::new(Mutex::new(HashMap::from([(
            "test-ticket".to_owned(),
            Pending { session: "test-session".to_owned(), sender: deliver },
        )])));
        let state = Arc::new(RelayState {
            token_hash: token_hash(token), pending: pending.clone(),
            connections: Arc::new(Semaphore::new(1)),
            public_bind: "127.0.0.1".parse().unwrap(), public_host: "127.0.0.1".to_owned(),
        });

        let (mut client, server) = tokio::io::duplex(4096);
        write_frame(&mut client, &Message::Data {
            version: VERSION, token: "wrong token".into(), ticket: "test-ticket".into(),
        }).await.unwrap();
        assert!(handle_relay_connection(Box::new(server), state.clone()).await.is_err());
        assert!(matches!(read_frame(&mut client).await.unwrap(), Message::Error { .. }));
        assert_eq!(pending_lock(&pending).len(), 1, "unauthenticated client must not consume ticket");
        assert!(matches!(receive.try_recv(), Err(oneshot::error::TryRecvError::Empty)));

        let (mut client, server) = tokio::io::duplex(4096);
        write_frame(&mut client, &Message::Data {
            version: VERSION, token: token.into(), ticket: "test-ticket".into(),
        }).await.unwrap();
        handle_relay_connection(Box::new(server), state.clone()).await.unwrap();
        assert!(matches!(read_frame(&mut client).await.unwrap(), Message::DataReady { .. }));
        let mut delivered = receive.await.unwrap();
        client.write_all(b"raw application bytes").await.unwrap();
        let mut buffer = [0_u8; 21];
        delivered.read_exact(&mut buffer).await.unwrap();
        assert_eq!(&buffer, b"raw application bytes");
        assert!(pending_lock(&pending).is_empty());

        let (mut client, server) = tokio::io::duplex(4096);
        write_frame(&mut client, &Message::Data {
            version: VERSION, token: token.into(), ticket: "test-ticket".into(),
        }).await.unwrap();
        assert!(handle_relay_connection(Box::new(server), state).await.is_err());
    }

    #[tokio::test]
    async fn cancelling_session_removes_only_its_tickets_and_disables_inserts() {
        let (owned_sender, owned_receiver) = oneshot::channel::<Stream>();
        let (other_sender, _other_receiver) = oneshot::channel::<Stream>();
        let pending = Arc::new(Mutex::new(HashMap::from([
            ("owned".into(), Pending { session: "cancelled".into(), sender: owned_sender }),
            ("other".into(), Pending { session: "surviving".into(), sender: other_sender }),
        ])));
        let active = Arc::new(AtomicBool::new(true));
        let guard = SessionGuard {
            pending: pending.clone(), session: "cancelled".into(), active: active.clone(),
        };
        let (started_sender, started_receiver) = oneshot::channel();
        let task = tokio::spawn(async move {
            let _guard = guard;
            started_sender.send(()).unwrap();
            std::future::pending::<()>().await;
        });
        started_receiver.await.unwrap();
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert!(!active.load(Ordering::Acquire));
        assert!(owned_receiver.await.is_err(), "cancelled session must close its waiting public socket");
        let remaining = pending_lock(&pending);
        assert_eq!(remaining.len(), 1);
        assert!(remaining.contains_key("other"));
    }
}
