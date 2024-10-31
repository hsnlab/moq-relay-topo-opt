#!/bin/bash

topology_file=$1

if [ -z "$topology_file" ]; then
    read -p "Please enter topo: " middle_part
    allowed_topologies="spineleaf line star"

    if [[ " $allowed_topologies " =~ " $middle_part " ]]; then
        topology_file="dev/topos/topo_${middle_part}.yaml"
    else
        echo "Invalid topology: $middle_part. Allowed values are $allowed_topologies."
        exit 1
    fi
fi

if [ "$topology_file" == "old" ]; then
    cp dev/topos/topo_old.yaml topo.yaml
    cp docker-compose-old.yml docker-compose.yml
    echo "Using old docker-compose configuration."
    exit 0
fi


relays=($(awk '/nodes:/,/edges:/{if (!/edges:/)print}' $topology_file | grep -v 'nodes:' | tr -d ' -'))

cp $topology_file topo.yaml


cat << EOF > docker-compose.yml
version: "3.8"

x-moq: &x-moq
  build: .
  environment:
    RUST_LOG: ${RUST_LOG:-debug}
  volumes:
    - ./dev/localhost.crt:/etc/tls/cert:ro
    - ./dev/localhost.key:/etc/tls/key:ro
    - certs:/etc/ssl/certs
  depends_on:
    install-certs:
      condition: service_completed_successfully

services:
  redis:
    image: redis:7
    ports:
    - "6400:6379"

  api:
    <<: *x-moq
    entrypoint: moq-api
    volumes:
      - ./topo.yaml:/topo.yaml:ro
    command: --redis redis://redis:6379 --topo-path topo.yaml
    ports:
      - "80"
  dir:
    <<: *x-moq
    entrypoint: moq-dir
    command: --tls-cert /etc/tls/cert --tls-key /etc/tls/key
    ports:
      - "443/udp"
EOF

for relay in "${relays[@]}"; do
cat << EOF >> docker-compose.yml
  relay${relay}:
    <<: *x-moq
    entrypoint: moq-relay
    command: --tls-cert /etc/tls/cert --tls-key /etc/tls/key --tls-disable-verify --api http://api --node https://relay${relay} --dev --announce https://dir --bind [::]:${relay}
    depends_on:
      - api
      - dir
    ports:
    - "${relay}:${relay}"
    - "${relay}:${relay}/udp"

EOF
done

cat << EOF >> docker-compose.yml
  install-certs:
    image: golang:latest
    working_dir: /work
    command: go run filippo.io/mkcert -install
    environment:
      CAROOT: /work/caroot
    volumes:
    - \${CAROOT:-.}:/work/caroot
    - certs:/etc/ssl/certs
    - ./dev/go.mod:/work/go.mod:ro
    - ./dev/go.sum:/work/go.sum:ro

volumes:
  certs:
EOF
