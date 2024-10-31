import os
import subprocess
import yaml
from functools import partial
from time import sleep
from sys import exit  # pylint: disable=redefined-builtin
import argparse
from mininet.net import Mininet
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.node import Node
from mininet.link import TCLink
from mininet import log
import os
import datetime
import glob
import re
import numpy as np
import re
import the_path


#!/usr/bin/env python
clocked = os.getenv("CLOCKED", False)
tls_verify = not os.getenv("NO_CERT", False)


def calculate_statistics(latencies):
    average = np.mean(latencies)
    median = np.median(latencies)
    percentile_99 = np.percentile(latencies, 99)
    return average/1e9, median/1e9, percentile_99/1e9

def extract_latency(line):
    match = re.search(r'Latency: (\d+)', line)
    if match:
        return int(match.group(1))
    return None



def main():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--filename', type=str, required=True, help='Filename for the output without .txt')
    parser.add_argument('--clock', action='store_true', help='Use clocked')
    parser.add_argument('--clockr', action='store_true', help='Use clocked')
    parser.add_argument('--tls-verify', action='store_true', help='Use tls_verify')
    parser.add_argument('--track', type=str, required=True, help='Track name')
    args = parser.parse_args()
    clocked = args.clock
    clockedr = args.clockr

    tls_verify = args.tls_verify

    setLogLevel('critical')
    template_for_relays = (
        'RUST_LOG=debug RUST_BACKTRACE=0 '
        './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
        '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
        ' {tls_verify} --dev {origi} &'
    )

    ip_string = ' '.join(['12.0.1.2 12.0.1.1 12.0.2.2 12.0.2.1'])
    with open('./dev/cert', 'r') as file:
        cert_content = file.readlines()
    cert_content[-1] = f'go run filippo.io/mkcert -ecdsa -days 10 -cert-file "$CRT" -key-file "$KEY" localhost 127.0.0.1 ::1  {ip_string}'
    with open('./dev/cert2', 'w') as file:
        file.writelines(cert_content)
    env = os.environ.copy()
    env['PATH'] =  env['PATH'] +the_path.PATH_GO
    subprocess.call(['./dev/cert2'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    tls_verify_str = ""
    tls_verify_gst_str=""
    if not tls_verify:
        tls_verify_str = "--tls-disable-verify"
        tls_verify_gst_str= "tls-disable-verify=true"

    filename = args.filename
    assumed_baseline = 0

    net = Mininet(topo=None, waitConnected=False, link=partial(TCLink))
    net.staticArp()

    # Create 3 hosts
    baseline_sub = net.addHost('h1', ip="")
    baseline_relay = net.addHost('h2', ip="")
    baseline_pub = net.addHost('h3', ip="")

    # Connect the hosts
    net.addLink(baseline_pub, baseline_relay,
                params1={'ip': f"12.0.1.1/24"},
                params2={'ip': f"12.0.1.2/24"})
    net.addLink(baseline_relay, baseline_sub,
                params1={'ip': f"12.0.2.2/24"},
                params2={'ip': f"12.0.2.1/24"})

    api = net.addHost('h999', ip="12.2.0.1")
    root = Node('root', inNamespace=False)
    intf = net.addLink(root, api).intf1
    root.setIP('12.2.0.99', intf=intf)
    net.addLink(
        api, baseline_relay, params1={'ip': f"12.1.0.1/24"}, params2={'ip': f"12.1.0.2/24"}
    )
    api.cmd('REDIS=12.2.0.99 ./dev/api --bind [::]:4442 &')

    net.start()
    baseline_sub.cmd('ip route add 12.0.1.0/30 via 12.0.2.2')
    baseline_pub.cmd('ip route add 12.0.2.0/30 via 12.0.1.2')

    # Start the relay on one of the hosts
    baseline_relay.cmd(template_for_relays.format(
        host=baseline_relay,
        bind='12.0.1.2:4443',
        api='http://12.1.0.1:4442',
        node='https://12.0.1.2:4443',
        tls_verify=tls_verify_str,
        origi="--original"
    ))
    sleep(1)
    # CLI(net)
    track = args.track
    if not clocked and not clockedr:
        vidi_filenammm = track.split("_")[1]
        baseline_pub.cmd(f'xterm -hold -T "baseline-pub" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; gst-launch-1.0 -q -v -e filesrc location="./dev/{vidi_filenammm}.mp4"  ! qtdemux name=before01 \
    before01.video_0 ! h264parse name=before02 ! avdec_h264 name=before03 ! videoconvert name=before2 ! timestampoverlay name=middle ! videoconvert name=after1 ! x264enc tune=zerolatency name=after2 ! h264parse name=after3 ! isofmp4mux chunk-duration=1 fragment-duration=1 name=after4 ! moqsink {tls_verify_gst_str} url="https://12.0.1.2:4443" namespace="{track}";sleep 0.1 "&')
        sleep(0.5)
        baseline_sub.cmd(f'xterm -hold -T "baseline-sub" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; export RST_LOG=debug; ./target/debug/moq-sub --name {track} https://12.0.1.2:4443 | GST_DEBUG=timeoverlayparse:4 gst-launch-1.0 --no-position filesrc location=/dev/stdin ! decodebin ! videoconvert ! timeoverlayparse ! videoconvert ! fakesink 2> measurements/assumed_baseline_pre_{filename}.txt" &')
        sleep(30) # should match with the normal measure
        subprocess.call(['sudo', 'pkill', '-f', 'xterm'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        lat =  f"measurements/assumed_baseline_pre_{filename}.txt"

        with open(lat, 'r') as file:
            file_latencies = []
            for line in file:
                latency = extract_latency(line)
                if latency is not None:
                    file_latencies.append(latency)
            if file_latencies:
                average, median, percentile_99 = calculate_statistics(file_latencies)
                assumed_baseline = average
                baseline_file = f"measurements/assumed_baseline_{filename}.txt"
                with open(baseline_file, 'w') as file:
                    file.write(str(assumed_baseline))
                print(f"*** assumed baseline: {assumed_baseline}")


    else:
        baseline_pub.cmd(f'xterm -hold  -T "baseline-pub" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --publish --namespace {track} https://12.0.1.2:4443" &')
        sleep(0.5)
        baseline_sub.cmd(f'xterm -hold  -T "baselin-sub" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --namespace {track} https://12.0.1.2:4443 {tls_verify_str} | tee measurements/assumed_baseline_clock_pre_{filename}.txt" &')
        sleep(30)
        subprocess.call(['sudo', 'pkill', '-f', 'xterm'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        file_path1 = f"measurements/assumed_baseline_clock_pre_{filename}.txt"
        with open(file_path1, 'r') as file:
            file_latencies = []
            for line in file:
                try:
                    number=int(line.strip())
                    if clocked:
                        latency = number*1000000
                        file_latencies.append(latency)
                    else:
                        if number<1000 and clockedr:
                            latency = number*1000000
                            file_latencies.append(latency)
                except ValueError:
                    #todo
                    continue
            if file_latencies:
                assumed_baseline, median, percentile_99 = calculate_statistics(file_latencies)
                print(f"*** assumed baseline (clocked): {assumed_baseline}")
                baseline_file = f"measurements/assumed_clocked_baseline_{filename}.txt"
                with open(baseline_file, 'w') as file:
                    file.write(str(assumed_baseline))
    net.stop()

    subprocess.call(['sudo', 'pkill', '-f', 'xterm'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
