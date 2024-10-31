use clap::Parser;
use server::{Server, ServerConfig};
use serde_yaml;
use serde::Deserialize;
use petgraph::graph::DiGraph;
use petgraph::algo::is_cyclic_directed;
use tokio::fs::File;
use env_logger;

use std::error::Error;

mod server;

#[derive(Debug, Deserialize)]
struct Topo {
    nodes: Vec<String>,
    edges: Vec<Vec<String>>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init();

    let config = ServerConfig::parse();
    let topo_path_str = config.topo_path.as_deref().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();

	if !topo_path_str.is_empty(){
		if !std::path::Path::new(&topo_path_str).exists() {
			log::info!("File path does not exist! Defaulting to full mesh.");
		}
		// TODO do a switcheroo with the true and false branches
		else{
			let topo_yaml = read_topology_file(&topo_path_str).await?;
			let topo: Topo = serde_yaml::from_str(&topo_yaml)?;

			validate_topology(&topo)?;

			log::info!("config: \n{}", topo_yaml);
		}
	} else {
		log::info!("File path is empty! Defaulting to full mesh.");
		// Set default value for topo_path_str here
	}

	let server = Server::new(config);
	server.run().await?;
    Ok(())
}

use tokio::io::AsyncReadExt;

async fn read_topology_file(file_path: &str) -> Result<String, Box<dyn Error>> {
    let mut file = File::open(file_path).await?;
    let mut contents = String::new();
    file.read_to_string(&mut contents).await?;
    Ok(contents)
}

fn validate_topology(topo: &Topo) -> Result<(), Box<dyn Error>> {
    for edge in &topo.edges {
        if edge.len() != 2 {
            return Err(Box::from("Edge is not valid!"));
        }
    }
	let graph = create_graph(&topo)?;

    if is_cyclic_directed(&graph) {
        return Err(Box::from("The graph is cyclic"));
    }
    Ok(())
}

fn create_graph(topo: &Topo) -> Result<DiGraph<(), ()>, Box<dyn Error>> {
    let mut graph = DiGraph::<(), ()>::new();
    let nodes: Vec<_> = topo.nodes.iter().map(|_| graph.add_node(())).collect();

    for edge in &topo.edges {
        let start = topo.nodes.iter().position(|n| n == &edge[0]).ok_or_else(|| Box::<dyn Error>::from("Node not found"))?;
        let end = topo.nodes.iter().position(|n| n == &edge[1]).ok_or_else(|| Box::<dyn Error>::from("Node not found"))?;
        graph.add_edge(nodes[start], nodes[end], ());
    }

    if is_cyclic_directed(&graph) {
        return Err(Box::from("The graph is cyclic"));
    }

    Ok(graph)
}
