#!/bin/bash
#https://github.com/bigswitch/mininet/blob/master/util/sysctl_addon

sysctl_configs=(
	"fs.file-max=100000"
	"net.core.wmem_max=16777216"
	"net.core.rmem_max=16777216"
	"net.core.netdev_max_backlog=5000"
	"net.ipv4.neigh.default.gc_thresh1=4096"
	"net.ipv4.neigh.default.gc_thresh2=8192"
	"net.ipv4.neigh.default.gc_thresh3=16384"
	"net.ipv4.route.max_size=32768"
	"fs.inotify.max_user_watches=524288"
	"fs.inotify.max_user_instances=512"
)

for config in "${sysctl_configs[@]}"; do
	sudo sysctl -w $config
done

# Apply multi-value sysctl configurations separately
echo "10240 87380 16777216" | sudo tee /proc/sys/net/ipv4/tcp_rmem
echo "10240 87380 16777216" | sudo tee /proc/sys/net/ipv4/tcp_wmem

echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor performance

