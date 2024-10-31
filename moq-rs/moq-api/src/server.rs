use std::{collections::{HashSet, VecDeque}, net};

use axum::{
	extract::{Path, State},
	http::StatusCode,
	response::{IntoResponse, Response},
	routing::{get,delete},
	Json, Router,
};

use clap::Parser;

use redis::{aio::ConnectionManager, AsyncCommands};

use moq_api::Origin;
use url::Url;
use serde::{Serialize,Deserialize};


/// Runs a HTTP API to create/get origins for broadcasts.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
pub struct ServerConfig {
	/// Listen for HTTP requests on the given address
	#[arg(long, default_value = "[::]:80")]
	pub bind: net::SocketAddr,

    /// Connect to the given redis instance
    #[arg(long)]
    pub redis: url::Url,

    /// Topology file contents
    #[arg(long)]
    pub topo_path: Option<std::path::PathBuf>,
}

impl ServerConfig {
	pub fn topo(&self) -> Result<Option<String>, std::io::Error> {
		if let Some(path) = &self.topo_path {
			Ok(Some(std::fs::read_to_string(path)?))
		} else {
			Ok(None)
		}
	}
}

pub struct Server {
	config: ServerConfig,
    topo: Option<String>,
}
#[derive(Clone)]
pub struct AppState {
    redis: ConnectionManager,
    topo: Option<String>,
}


impl Server {
	pub fn new(config: ServerConfig) -> Self {
		let topo = match config.topo() {
			Ok(s) => s,
			Err(_e) => {
				return Self { config, topo: None };
			}
		};

		Server { config, topo }
	}

	pub async fn run(self) -> Result<(), Box<dyn std::error::Error>> {
		log::info!("connecting to redis: url={}", self.config.redis);

		// Create the redis client.
		let redis = redis::Client::open(self.config.redis)?;
		let redis = redis.get_connection_manager().await?;

		// here it should be checked if the topo is none or not
		// if it is none, then this should happen
		let app;
		if self.topo.is_none() {
			log::debug!("topo is none");
			app = Router::new()
				.route(
					"/origin/*namespace",
					get(get_origin)
						.post(set_origin)
						.delete(delete_origin)
						.patch(patch_origin),
				)
				.with_state(
					redis
				);
		} else {
			log::debug!("topo is not none");
			app = Router::new()
				.route(
					"/origin/:relayid/*namespace",
					get(get_origin2).post(set_origin2),
				)
				.route(
					"/origin/:id",
					delete(delete_origin2).patch(patch_origin2),
				)
				.with_state(AppState {
					redis,
					topo: self.topo,
				});
		}


		log::info!("serving requests: bind={}", self.config.bind);

		let listener = tokio::net::TcpListener::bind(&self.config.bind).await?;
		axum::serve(listener, app.into_make_service()).await?;

		Ok(())
	}
}

async fn get_origin2(
	Path((relayid, namespace)): Path<(String, String)>,
	State(mut state): State<AppState>,
) -> Result<Json<Origin>, AppError> {
	let key = origin_key2(&namespace, &relayid);

	let payload: Option<String> = state.redis.get(&key).await?;
	let payload = payload.ok_or(AppError::NotFound)?;
	let origin: Origin = serde_json::from_str(&payload)?;
	Ok(Json(origin))
}

#[derive(Debug, Deserialize, Serialize)]
struct Topology {
    nodes: Vec<String>,
    edges: Vec<(String, String)>,
}

async fn set_origin2(
    State(mut state): State<AppState>,
	Path((relayid, namespace)): Path<(String, String)>,
    Json(origin): Json<Origin>,
) -> Result<(), AppError> {

    let topo_str = state.topo.as_deref().ok_or(AppError::Parameter(url::ParseError::IdnaError))?;
    let topo: Topology = serde_yaml::from_str(topo_str).map_err(|_| AppError::Parameter(url::ParseError::IdnaError))?;
	if !topo.nodes.contains(&relayid) {
		log::warn!("!!!not the expected publisher relay {}", relayid);
		return Err(AppError::Parameter(url::ParseError::IdnaError));
	}

	let mut preinfo: Vec<(String, String)> = Vec::new();
    let mut queue: VecDeque<String> = VecDeque::new();
    let mut visited: HashSet<String> = HashSet::new();

	let mut relayid = relayid.clone();
	if let Some((ip, _)) = relayid.split_once('_') {
        if let Some(last_octet) = ip.split('.').last() {
            relayid= last_octet.to_string();
        }
    }
    queue.push_back(relayid.clone());
    visited.insert(relayid.clone());


	// Getting the edges that will be used for that exact relayid
    while let Some(node) = queue.pop_front() {
        for (from, to) in &topo.edges {
            if from == &node && !visited.contains(to) {
                preinfo.push((to.to_string(), from.to_string()));
                queue.push_back(to.clone());
                visited.insert(to.clone());
            } else if to == &node && !visited.contains(from) {
                preinfo.push((from.to_string(), to.to_string()));
                queue.push_back(from.clone());
                visited.insert(from.clone());
            }
        }
    }

	//for docker reasons right now we have to provide the hostname also
	let mut relay_info: Vec<(String, String, u16)> = Vec::new();
	for (src, dest) in preinfo {
		relay_info.push((src.to_string(), "10.3.0.".to_owned()+&dest.clone(), 4443));
	}


	for (src_key_id, dst_host, dst_port) in relay_info.into_iter() {
        let key = origin_key2(&namespace, &src_key_id);
        let mut url = Url::parse(&origin.url.to_string()).unwrap();

		let _ = url.set_port(Some(dst_port));
		let _ = url.set_host(Some(&dst_host));

        let new_origin = Origin {
            url: Url::parse(&url.to_string()).unwrap(),
        };
        let payload = serde_json::to_string(&new_origin)?;

        // Attempt to get the current value for the key
        let current: Option<String> = redis::cmd("GET").arg(&key).query_async(&mut state.redis).await?;

        if let Some(current) = &current {
            if current.eq(&payload) {
                // The value is the same, so we're done.
                continue;
            } else {
                return Err(AppError::Duplicate);
            }
        }

        let res: Option<String> = redis::cmd("SET")
            .arg(key)
            .arg(payload)
            .arg("NX")
            .arg("EX")
            .arg(600) // Set the key to expire in 10 minutes; the origin needs to keep refreshing it.
            .query_async(&mut state.redis)
            .await?;

        if res.is_none() {
            return Err(AppError::Duplicate);
        }
    }

    Ok(())
}

async fn delete_origin2(
	Path(namespace): Path<String>,
	State(mut state): State<AppState>,
) -> Result<(), AppError> {
	let key = format!("*{}", namespace);
	match state.redis.del(key).await? {
		0 => Err(AppError::NotFound),
		_ => Ok(()),
	}
}

// Update the expiration deadline.
async fn patch_origin2(
	Path(namespace): Path<String>,
	State(mut state): State<AppState>,
	Json(origin): Json<Origin>,
) -> Result<(), AppError> {
    let pattern = format!("*{}", namespace);
    let keys: Vec<String> = redis::cmd("KEYS").arg(&pattern).query_async(&mut state.redis).await?;
	// Make sure the contents haven't changed
	// TODO make a LUA script to do this all in one operation.
	for key in keys {
		let payload: Option<String> = state.redis.get(&key).await?;
		let payload = payload.ok_or(AppError::NotFound)?;
		let expected: Origin = serde_json::from_str(&payload)?;

		if expected != origin {
			return Err(AppError::Duplicate);
		}
	}

	Ok(())

}



fn origin_key2(namespace: &str,relayid: &str) -> String {
	format!("origin.{}.{}",relayid, namespace)
}



async fn get_origin(
	Path(namespace): Path<String>,
	State(mut redis): State<ConnectionManager>,
) -> Result<Json<Origin>, AppError> {
	let key = origin_key(&namespace);

	let payload: Option<String> = redis.get(&key).await?;
	let payload = payload.ok_or(AppError::NotFound)?;
	let origin: Origin = serde_json::from_str(&payload)?;

	Ok(Json(origin))
}

async fn set_origin(
	State(mut redis): State<ConnectionManager>,
	Path(namespace): Path<String>,
	Json(origin): Json<Origin>,
) -> Result<(), AppError> {
	// TODO validate origin

	let key = origin_key(&namespace);

	// Convert the input back to JSON after validating it add adding any fields (TODO)
	let payload = serde_json::to_string(&origin)?;

	// Attempt to get the current value for the key
	let current: Option<String> = redis::cmd("GET").arg(&key).query_async(&mut redis).await?;

	if let Some(current) = &current {
		if current.eq(&payload) {
			// The value is the same, so we're done.
			return Ok(());
		} else {
			return Err(AppError::Duplicate);
		}
	}

	let res: Option<String> = redis::cmd("SET")
		.arg(key)
		.arg(payload)
		.arg("NX")
		.arg("EX")
		.arg(600) // Set the key to expire in 10 minutes; the origin needs to keep refreshing it.
		.query_async(&mut redis)
		.await?;

	if res.is_none() {
		return Err(AppError::Duplicate);
	}

	Ok(())
}

async fn delete_origin(
	Path(namespace): Path<String>,
	State(mut redis): State<ConnectionManager>,
) -> Result<(), AppError> {
	let key = origin_key(&namespace);
	match redis.del(key).await? {
		0 => Err(AppError::NotFound),
		_ => Ok(()),
	}
}

// Update the expiration deadline.
async fn patch_origin(
	Path(namespace): Path<String>,
	State(mut redis): State<ConnectionManager>,
	Json(origin): Json<Origin>,
) -> Result<(), AppError> {
	let key = origin_key(&namespace);

	// Make sure the contents haven't changed
	// TODO make a LUA script to do this all in one operation.
	let payload: Option<String> = redis.get(&key).await?;
	let payload = payload.ok_or(AppError::NotFound)?;
	let expected: Origin = serde_json::from_str(&payload)?;

	if expected != origin {
		return Err(AppError::Duplicate);
	}

	// Reset the timeout to 10 minutes.
	match redis.expire(key, 600).await? {
		0 => Err(AppError::NotFound),
		_ => Ok(()),
	}
}


fn origin_key(namespace: &str) -> String {
	format!("origin.{}", namespace)
}

#[derive(thiserror::Error, Debug)]
enum AppError {
	#[error("redis error")]
	Redis(#[from] redis::RedisError),

	#[error("json error")]
	Json(#[from] serde_json::Error),


	#[error("yaml error")]
	Yaml(#[from] serde_yaml::Error),

	#[error("not found")]
	NotFound,

	#[error("duplicate ID")]
	Duplicate,

	#[error("url error in parameter: {0}")]
	Parameter(#[from] url::ParseError),
}

// Tell axum how to convert `AppError` into a response.
impl IntoResponse for AppError {
	fn into_response(self) -> Response {
		match self {
			AppError::Redis(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("redis error: {}", e)).into_response(),
			AppError::Json(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("json error: {}", e)).into_response(),
			AppError::Yaml(e) => (StatusCode::INTERNAL_SERVER_ERROR, format!("yaml error: {}", e)).into_response(),
			AppError::NotFound => StatusCode::NOT_FOUND.into_response(),
			AppError::Duplicate => StatusCode::CONFLICT.into_response(),
			AppError::Parameter(e) => (StatusCode::BAD_REQUEST, format!("parameter error: {}", e)).into_response(),
		}
	}
}
