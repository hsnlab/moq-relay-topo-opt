sudo apt-get update

sudo apt install -y tzdata python3 python3-pip ninja-build libsoup2.4-1 libsoup2.4-dev libssl3 \
   libssl-dev libsrtp2-1 libsrtp2-dev libgnutls30 libgnutls28-dev \
   libgnutls-openssl27 libnice10 libnice-dev libwebsockets16 libwebsockets-dev \
   flex bison libpango-1.0-0 libpango1.0-dev libpango-1.0-0 libpango1.0-dev \
   libpangocairo-1.0-0 libjson-glib-1.0-0 libjson-glib-dev libavfilter7 \
   libavfilter-dev libavformat58 libavformat-dev libavcodec58 libavcodec-dev \
   libavutil56 libavutil-dev libgtk-3-dev libtool git libusrsctp2 curl \
   mininet xterm python3.10-venv python-is-python3 ffmpeg python3-numpy htop
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
. "$HOME/.cargo/env"

sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

wget https://go.dev/dl/go1.23.1.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.23.1.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go
echo "export PATH=$PATH:/usr/local/go" >> ~/.bashrc
sudo pip3 install --no-cache-dir -Iv meson==0.62
git clone --depth=1 --branch 1.22 https://gitlab.freedesktop.org/gstreamer/gstreamer.git
cd gstreamer
mkdir build
echo "!!!! kell egy meson path "
meson --prefix=/usr build \
  -Dgpl=enabled \
  -Drs=disabled \
  -Dlibav=enabled \
  -Dgst-plugins-ugly:x264=enabled \
  -Dgst-plugins-base:pango=enabled \
  -Ddevtools=disabled \
  -Dtests=disabled \
  -Dexamples=disabled \
  -Ddoc=disabled \
  -Dorc=disabled \
  -Dlibsoup:sysprof=disabled \
  -Dbuildtype=release
ninja -C build
meson install -C build
cd ..
git clone https://github.com/kixelated/moq-gst
cd moq-gst
cargo build
cd ..
git clone --depth=1 https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs
cd gst-plugins-rs/mux/fmp4
cargo build --release
cp ../../target/release/libgstfmp4.so ../../../moq-gst/target/debug/
cd ../../../
git clone https://github.com/SNS-JU/6gxr-latency-clock.git
cd 6gxr-latency-clock/
git checkout f629e06991425a7e250bb3a771fa9c211cde0c08
make
cd ..
git clone https://github.com/Zotyamester/cdn-optimization
cd cdn-optimization
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install basemap
cd ..
git clone https://github.com/1majom/moq-rs --branch dep_on_smart
cd moq-rs
cargo build
mkdir measurements
sudo chmod +x ./dev/cert2

# perf
# echo `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq` | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq


echo "download this into moq-rs/dev/ https://bmeedu-my.sharepoint.com/:f:/g/personal/szenczy_balazs_edu_bme_hu/EuF3XVMjam9Ll2wUtFLoHC0BdTF_WY7xuZXNyH5xW4RqMg?e=9krJTt"
