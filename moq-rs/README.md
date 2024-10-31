
### About this branch

This project tries to put the very well written Media over QUIC implementation, moq-rs into a custom topology inside mininet. Before the changes of moqtransfork.
The project is closely connected to [Zotyamester/cdn-optimizer](https://github.com/Zotyamester/cdn-optimization) (later referenced as cdn-opti) which can be used as an alternative api instead of the moq-api provided by the original project. The main difference between these that with moq-api the subscriber's relay will always get the publisher's relay without any inbetween relays, only using one link from our relay mesh network. The cdn-opti instead will use the provided costs to calculate a more optimal route while using more then 1 links.

For the whole project to work on a fresh **Ubuntu 22.04** machine the vm_start.sh file should be downloaded alone and ran in the folder where we want to see the moq-rs and other projects folders. Also a the_path.py file is needed to be created inside that we the following. And also a venv variable which is all is correctly set up should be the command activating the venv under the venv folder.
```
PATH_GO=# ':' and the path to go
venv=# source and the venv activate file or nothing if the needed python modules for the cdn-opti are installed systemwide
user=# insert echo $USER here
cargopath=# the path to the cargo bin
test_set = [
	#the wanted tests as a list of tuples, first the topology file, then the wanted API (origi or opti), and lastly clock or gst, latter is better right now
	#two examples
    # ("small_topo_ps.yaml","origi", "gst"),
    # ("small_topo_ps_yaml","opti", "gst"), 
]
# the following are wait times
wait_between_pubs=3
wait_after_pubs=2
wait_between_subs=0.8
```

Right now to start the good_try.py mininet script we need a topology file. These topology files are gotten from the cdn-opti repo which should be cloned next to this one so it can be reached.
Here is a sample topology file:
```
first_hop_relay:
  - relayid: "node1"
    track: "bbb-720_1000"
last_hop_relay:
  - relayid: "node2"
    track: "bbb-720_1000"

nodes:
  - name: "node1"
    location:
      - 40.7128
      - -74.0060
  - name: "node2"
    location:
      - 37.7749
      - -122.4194

edges:
  - node1: "node1"
    node2: "node2"
    attributes:
      latency: 0
      cost: 0.01
	  underlay_length: 1
```

- nodes: are the relays, which can be used in edges, also the length of this list will imply how many relays are there in the topology

- edges: are the connections between the relays. the provided latency will be applied to the mininet topology, and the cost will be used by the cdn-opti api, the underlay_length will be used when evaluating the measurements

- in the following list we can provide the publishers by specifying their starting relay and the track name that they will use

- it is important that the trackname should follow the following naming convention: 
  - {id, with one publisher it is not needed}\_{the filename of the wanted video w/o .mp4}\_{the cost budget that the cdn-opti should use}

- filename provided by downloading the video files (the first few are converted to that resolution, the latter ones are cut to 30secs) from the vm_start.sh:

  - bbb-{720|480|360|720-30|480-30|360-30}

- its important that each relay can only have 1 publisher/subscriber when using the cdn-opti
- All used topology files can be found in cdn-opti repo under the datasources folder

Bellow we can see the original readme of the moq-rs project.


***


<p align="center">
	<img height="128px" src="https://github.com/kixelated/moq-rs/blob/main/.github/logo.svg" alt="Media over QUIC">
</p>

Media over QUIC (MoQ) is a live media delivery protocol utilizing QUIC streams.
See [quic.video](https://quic.video) for more information.

This repository contains a few crates:

-   **moq-relay**: Accepting content from publishers and serves it to any subscribers.
-   **moq-pub**: Publishes fMP4 broadcasts.
-   **moq-transport**: An implementation of the underlying MoQ protocol.
-   **moq-api**: A HTTP API server that stores the origin for each broadcast, backed by redis.
-   **moq-dir**: Aggregates announcements, used to discover broadcasts.
-   **moq-clock**: A dumb clock client/server just to prove MoQ is more than media.

There's currently no way to view media with this repo; you'll need to use [moq-js](https://github.com/kixelated/moq-js) for that.
A hosted version is available at [quic.video](https://quic.video) and accepts the `?host=localhost:4443` query parameter.

# Development

Launch a basic cluster, including provisioning certs and deploying root certificates:

```
make run
```

Then, visit https://quic.video/publish/?server=localhost:4443.

For more control, use the [dev helper scripts](dev/README.md).

# Usage

## moq-relay

[moq-relay](moq-relay) is a server that forwards subscriptions from publishers to subscribers, caching and deduplicating along the way.
It's designed to be run in a datacenter, relaying media across multiple hops to deduplicate and improve QoS.
The relays optionally register themselves via the [moq-api](moq-api) endpoints, which is used to discover other relays and share broadcasts.

Notable arguments:

-   `--bind <ADDR>` Listen on this address, default: `[::]:4443`
-   `--tls-cert <CERT>` Use the certificate file at this path
-   `--tls-key <KEY>` Use the private key at this path
-   `--announce <URL>` Forward all announcements to this instance, typically [moq-dir](moq-dir).

This listens for WebTransport connections on `UDP https://localhost:4443` by default.
You need a client to connect to that address, to both publish and consume media.

## moq-pub

A client that publishes a fMP4 stream over MoQ, with a few restrictions.

-   `separate_moof`: Each fragment must contain a single track.
-   `frag_keyframe`: A keyframe must be at the start of each keyframe.
-   `fragment_per_frame`: (optional) Each frame should be a separate fragment to minimize latency.

This client can currently be used in conjuction with either ffmpeg or gstreamer.

### ffmpeg

moq-pub can be run as a binary, accepting a stream (from ffmpeg via stdin) and publishing it to the given relay.
See [dev/pub](dev/pub) for the required ffmpeg flags.

### gstreamer

moq-pub can also be run as a library, currently used for a [gstreamer plugin](https://github.com/kixelated/moq-gst).
This is in a separate repository to avoid gstreamer being a hard requirement.
See [run](https://github.com/kixelated/moq-gst/blob/main/run) for an example pipeline.

## moq-transport

A media-agnostic library used by [moq-relay](moq-relay) and [moq-pub](moq-pub) to serve the underlying subscriptions.
It has caching/deduplication built-in, so your application is oblivious to the number of connections under the hood.

See the published [crate](https://crates.io/crates/moq-transport) and [documentation](https://docs.rs/moq-transport/latest/moq_transport/).

## moq-clock

[moq-clock](moq-clock) is a simple client that can publish or subscribe to the current time.
It's meant to demonstate that [moq-transport](moq-transport) can be used for more than just media.

## moq-dir

[moq-dir](moq-dir) is a server that aggregates announcements.
It produces tracks based on the prefix, which are subscribable and can be used to discover broadcasts.

For example, if a client announces the broadcast `.public.room.12345.alice`, then `moq-dir` will produce the following track:

```
TRACK namespace=. track=public.room.12345.
OBJECT +alice
```

Use the `--announce <moq-dir-url>` flag when running the relay to forward all announcements to the instance.

## moq-api

This is a API server that exposes a REST API.
It's used by relays to inserts themselves as origins when publishing, and to find the origin when subscribing.
It's basically just a thin wrapper around redis that is only needed to run multiple relays in a (simple) cluster.

# License

Licensed under either:

-   Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
-   MIT license ([LICENSE-MIT](LICENSE-MIT) or http://opensource.org/licenses/MIT)
