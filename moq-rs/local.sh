#!/bin/bash

cleanup() {
    echo "Stopping all background processes..."
    pkill -f './target/debug/moq-api'
    pkill -f './target/debug/moq-relay'
    pkill -f './target/debug/moq-pub'
    pkill -f './target/debug/moq-sub'
}

trap cleanup SIGINT SIGTERM

REDIS=127.0.0.1 ./dev/api --bind 127.0.0.1:4442 &
RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '127.0.0.1:4444' --node 'https://127.0.0.1:4444' --api http://127.0.0.1:4442 --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --original --dev &
RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-relay --bind '127.0.0.1:4445' --node 'https://127.0.0.1:4445' --api http://127.0.0.1:4442 --tls-cert dev/localhost.crt --tls-key dev/localhost.key --tls-disable-verify --original --dev &

# ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/bbb.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - | RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-pub --name bbb3 https://127.0.0.1:4444 --tls-disable-verify &
# RUST_LOG=debug RUST_BACKTRACE=1 ./target/debug/moq-sub --name bbb3 https://127.0.0.1:4445 --tls-disable-verify | ffplay -x 200 -y 100  -
# might help: -framedrop


wait
