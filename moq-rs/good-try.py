#!/usr/bin/python

import os
import subprocess
import yaml
from functools import partial
from time import sleep
from sys import exit  # pylint: disable=redefined-builtin

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
import os
import datetime
import subprocess
import json
import the_path
import networkx as nx
from collections import Counter

my_debug = os.getenv("MY_DEBUG", False)
all_gas_no_brakes= not os.getenv("BRAKE", False)
video_on = os.getenv("LOOKY", False)
forklift_certified = not os.getenv("NO_CERT", False)
num_of_tries = int(os.getenv("NUMERO", 1))
no_based_line = os.getenv("NO_BASE", False)
gst_shark = int(os.getenv("SHARK", 0))
topofile= os.getenv("TOPO", "tiniest_topo.yaml")
folding= os.getenv("BUILD", False)
# gst mostly, clock for moq-clock, clockr cuts off seconds of first delays, ffmpeg for no measurement
mode = os.getenv("MODE", "clock")


def info(msg):
    log.info(msg + '\n')

def debug(msg):
    if my_debug:
        log.info(msg + '\n')

def relayid_to_ip(relayname, node_names):
    relayid = node_names.index(relayname) + 1
    return f"10.3.0.{relayid}"

def calculate_statistics(latencies):
    average = np.mean(latencies)
    std_dev = np.std(latencies)
    median = np.median(latencies)
    percentile_99 = np.percentile(latencies, 99)
    return average/1e9, std_dev/1e9,median/1e9, percentile_99/1e9
def extract_latency(line):
    match = re.search(r'(\d+),', line)
    if match:
        return int(match.group(1))
    return None

if not os.geteuid() == 0:
    exit("** This script must be run as root")

if not os.path.exists('the_path.py'):
    exit("** the_path module is not available")

test_set = the_path.test_set
test_set_unique = list(set(item[0] for item in test_set))

# Checking all the topo files if they have all the edges
for topo in test_set_unique:
    with open(f"../cdn-optimization/datasource/{topo}", 'r') as file:
        config = yaml.safe_load(file)
    node_names = [node['name'] for node in config['nodes']]

    G = nx.Graph()
    G.add_nodes_from(node_names)
    for edge in config['edges']:
        G.add_edge(edge['node1'], edge['node2'])
    is_full_mesh = all(G.has_edge(node1, node2) for node1 in node_names for node2 in node_names if node1 != node2)

    if not is_full_mesh:
        raise ValueError(f"The nodes and edges do not form a full mesh in {topo}")
if __name__ == '__main__':

    for topo_idx in range(len(test_set)):
        for try_idx in range(num_of_tries):
            print("** Mopping up remaining mininet")

            subprocess.call(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['sudo', 'pkill', '-f','gst-launch'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.call(['sudo', 'pkill', '-f','xterm'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if my_debug or folding:
                print("** Folding them needed binaries")
                subprocess.run(['rm', 'target/debug/*'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['sudo', '-u', the_path.user, the_path.cargopath, 'build'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            sleep(5)


            if my_debug:
                setLogLevel( 'info' )
            else:
                setLogLevel( 'critical' )
            current_time1 = datetime.datetime.now().strftime("%Y%m%d%H%M%S")



            topofile = test_set[topo_idx][0]
            with open(f"../cdn-optimization/datasource/{topofile}", 'r') as file:
                config = yaml.safe_load(file)
            config['mode'] = test_set[topo_idx][2] if len(test_set[topo_idx]) > 2 else mode
            config['api'] = test_set[topo_idx][1]
            print(f"** Sorting out the config {topofile} with {config['mode']} and {config['api']}")

            baseline_clk_str = ""
            baseline_tls_str = ""
            baseline_path_clk_str = ""
            if config['mode'] in ['clock', 'clockr']:
                baseline_clk_str = f"--{config['mode']}"
                baseline_path_clk_str = "clocked_"
            if forklift_certified:
                baseline_tls_str = "--tls-verify"

            baseline_path = os.path.join('measurements', f"assumed_{baseline_path_clk_str}baseline_{current_time1}.txt")
            based_line = 0.0
            if not no_based_line:
                subprocess.call(['sudo', 'python', 'base_try.py', '--filename', f"{current_time1}",'--track',f"{config['first_hop_relay'][0]['track']}"] + ([baseline_clk_str] if baseline_clk_str else []) + ([baseline_tls_str] if baseline_tls_str else []))
                with open(baseline_path, 'r') as file:
                    baseline_content = file.read().strip()
                    based_line = float(baseline_content)
            else:
                print("** No baseline because debugging NO_BASE envvar")
                based_line = 0.0
                with open(baseline_path, 'w') as file:
                    file.write(str(based_line))


            net = Mininet( topo=None, waitConnected=True, link=partial(TCLink) )
            net.staticArp()
            switch = net.addSwitch('s1',failMode='standalone')


            relay_number = len(config['nodes'])


            node_names = [item['name'] for item in config['nodes']]
            edges = config['edges']
            connections = []
            for edge in edges:
                src = edge['node1']
                dst = edge['node2']
                src_index = node_names.index(src) + 1
                dst_index = node_names.index(dst) + 1
                latency = edge['attributes']['latency']
                connection = {'node1': src_index, 'node2': dst_index, 'delay': latency}
                connections.append(connection)
                debug(f"I see {src} to {dst} at index {connection['node1']} and {connection['node2']} with latency {connection['delay']}ms")
            edges = connections


            # print("** Baking fresh cert")
            ip_string = ' '.join([f'10.3.0.{i}' for i in range(1, relay_number+1)])
            with open('./dev/cert', 'r') as file:
                cert_content = file.readlines()
            cert_content[-1] = f'go run filippo.io/mkcert -ecdsa -days 10 -cert-file "$CRT" -key-file "$KEY" localhost 127.0.0.1 ::1  {ip_string}'
            with open('./dev/cert2', 'w') as file:
                file.writelines(cert_content)
            env = os.environ.copy()
            env['PATH'] =  env['PATH'] + the_path.PATH_GO
            subprocess.call(['./dev/cert2'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            """
            the different networks are:
            - 10.0.x.0/24 - relay to relay connections where x is a counter
            - 10.1.1.0/24 - api network
            - 10.2.0.0/24 - api to host os connection (for docker)
            - 10.3.0.0/24 - relay identifying ips, on the lo interface of the relays
            - 10.4.x.0/24 - pub and sub to relay connections, where x is a counter
            the first_hop_relay is the relay which the pub will use
            the last_hop_relay is the relay which the sub(s) will use (with 3 subs the third will fail, if sleep is higher than 0.2)
            """

            first_hop_relay = [(relayid_to_ip(item['relayid'], node_names), item['track']) for item in config['first_hop_relay']]
            last_hop_relay = [(relayid_to_ip(item['relayid'], node_names), item['track']) for item in config['last_hop_relay']]

            number_of_clients = len(last_hop_relay)+len(first_hop_relay)
            relays = []
            pubs = []
            subs= []
            k = 1


            # ** Creating hosts
            for i in range(relay_number):
                host = net.addHost(f'h{k}', ip="")
                host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
                relays.append(host)

                k += 1

            for i in range(len(first_hop_relay)):
                host = net.addHost(f'h{k}', ip="")
                host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
                pubs.append((host,first_hop_relay[i][1]))

                k += 1

            for i in range(len(last_hop_relay)):
                host = net.addHost(f'h{k}', ip="")
                host.cmd('ip addr add 10.3.0.%s/32 dev lo' % str((k)))
                subs.append((host,last_hop_relay[i][1]))

                k += 1


            # *** Setting up full mesh network
            network_counter = 0
            delay = None
            # *** connecting pubs and subs
            pub_relays = {}
            for i in range(relay_number):
                matching_pubs = [g for g, (ip, _) in enumerate(first_hop_relay) if ip.split('.')[-1] == str(i+1)]
                for index in matching_pubs:
                    net.addLink( pubs[index][0],relays[i],
                        params1={'ip': f"10.4.{network_counter}.{2*index+1}/24"},
                        params2={'ip':  f"10.4.{network_counter}.{2*index+2}/24"})
                    pubs[index][0].cmd(f'ip route add 10.3.0.{i+1}/32 via 10.4.{network_counter}.{2*index+2}')
                    debug(f'ip route add 10.3.0.{i+1}/32 via 10.4.{network_counter}.{2*index+2}')
                    network_counter += 1
                    pub_relays[str(pubs[index][1])]=(relays[i])

                matching_subs = [g for g, (ip, _) in enumerate(last_hop_relay) if ip.split('.')[-1] == str(i+1)]
                for index in matching_subs:
                    net.addLink( subs[index][0],relays[i],
                        params1={'ip': f"10.5.{network_counter}.{2*index+1}/24"},
                        params2={'ip':  f"10.5.{network_counter}.{2*index+2}/24"})
                    subs[index][0].cmd(f'ip route add 10.3.0.{i+1}/32 via 10.5.{network_counter}.{2*index+2}')
                    debug(f'ip route add 10.3.0.{i+1}/32 via 10.5.{network_counter}.{2*index+2}')
                    network_counter += 1

            # *** connecting relays to each other adding delays
            for i in range(relay_number):
                for j in range(i + 1, relay_number):
                    searching = True
                    for edge in edges:
                        if ((i+1 == edge['node1'] and j+1 == edge['node2']) or (i+1 == edge['node2'] and j+1 == edge['node1'])) and searching:
                            delay=edge['delay']
                            debug(f"delay between {i+1} and {j+1} is {delay}")
                            searching=False
                            # break
                    ip1 = f"10.0.{network_counter}.1/24"
                    ip2 = f"10.0.{network_counter}.2/24"

                    host1 = relays[i]
                    host2 = relays[j]
                    if delay is None:
                        net.addLink(host1, host2, cls=TCLink,
                        params1={'ip': ip1},
                        params2={'ip': ip2})
                    else:
                        net.addLink(host1, host2, cls=TCLink, delay=f'{delay}ms',
                        params1={'ip': ip1},
                        params2={'ip': ip2})
                        info(f"\n")

                    ip1 = f"10.0.{network_counter}.1"
                    ip2 = f"10.0.{network_counter}.2"
                    host1.cmd(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
                    host2.cmd(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
                    debug(f'ip route add 10.3.0.{j+1}/32 via {ip2}')
                    debug(f'ip route add 10.3.0.{i+1}/32 via {ip1}')
                    network_counter += 1
                    delay=None


            api = net.addHost('h999', ip="10.2.0.1")
            root = Node( 'root', inNamespace=False )
            intf = net.addLink( root, api ).intf1
            root.setIP( '10.2.0.99', intf=intf )

            # *** Setting up "api network"
            ip_counter = 1
            net.addLink(
                 api,switch,params1 = {'ip': f"10.1.1.{ip_counter}/24"},
            )
            ip_counter += 1
            for host in relays:
                    net.addLink(
                        host, switch, params1 = {'ip': f"10.1.1.{ip_counter}/24"},
                    )
                    ip_counter += 1

            current_time = datetime.datetime.now().strftime("%m%d%H%M%S")

            net.start()

            if my_debug:
                dumpNodeConnections(net.hosts)
                info("pubs: " + str(pubs))
                info("subs: " + str(subs))

            template_for_relays = (
                    'RUST_LOG=debug RUST_BACKTRACE=0 '
                    './target/debug/moq-relay --bind \'{bind}\' --api {api} --node \'{node}\' '
                    '--tls-cert ./dev/localhost.crt --tls-key ./dev/localhost.key '
                    ' {tls_verify} --dev {origi} &'
                )

            origi_api_str = ""
            if config['api'] == "origi":
                origi_api_str = "--original"
                api.cmd('REDIS=10.2.0.99 ./dev/api --bind [::]:4442 &')
            else:
                if config['api'] == "opti":
                    api.cmd(f'cd ../cdn-optimization;{the_path.venv} TOPOFILE={topofile} python -m fastapi dev app/api.py --host 10.1.1.1 --port 4442 &')

            # for some reason this is needed or the first relay wont reach the api
            # (ffmpeg needs the 1s, gst can work with less)
            sleep(4)


            tls_verify_str = ""
            if not forklift_certified:
                tls_verify_str = "--tls-disable-verify"

            host_counter = 1
            for h in relays:
                ip_address = f'10.3.0.{host_counter}'
                debug(f'Starting relay on {h} - {ip_address}')

                h.cmd(template_for_relays.format(
                    host=h.name,
                    bind=f'{ip_address}:4443',
                    api=f'http://10.1.1.1:4442',
                    node=f'https://{ip_address}:4443',
                    tls_verify=tls_verify_str,
                    origi=origi_api_str
                ))
                debug(template_for_relays.format(
                    host=h.name,
                    bind=f'{ip_address}:4443',
                    api=f'http://10.1.1.1:4442',
                    node=f'https://{ip_address}:4443',
                    tls_verify=tls_verify_str,
                    origi=origi_api_str
                ))

                host_counter += 1


            # the two sleeps are needed at that specific line, bc other way they would start and the exact same time,
            # and the pub wouldn't connect to the relay, and the sub couldn't connect to the pub
            sleep(0.5)
            k=0
            def get_video_duration(file_path):
                command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
                output = subprocess.check_output(command).decode().strip()
                duration = float(output)
                return duration

            max_video_duration = 0
            max_resolution = 300

            for (h,track) in pubs:
                vidi_filenammm = track.split("_")[1]
                if config['mode'] == 'gst':

                    track_duration = get_video_duration(f"./dev/{vidi_filenammm}.mp4")
                    if track_duration > max_video_duration:
                        max_video_duration = track_duration
                else:
                    if config['mode'] in ['clock', 'clockr']:
                        try:
                            max_video_duration = int(vidi_filenammm.split("-")[2])
                        except:
                            max_video_duration = 30

                resolution = track.split("_")[1].split("-")[1]
                if int(resolution) > max_resolution:
                    max_resolution = int(resolution)
                le_cmd = ""

                if config['mode'] in ['clock', 'clockr']:
                    le_cmd = (f'xterm -hold  -T "{h.name}-pub" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --publish --namespace {track} https://{first_hop_relay[k][0]}:4443 {tls_verify_str}" &')
                else:
                    if config['mode'] == 'ffmpeg':
                        le_cmd = (f'xterm -hold -T "{h.name}-pub" -e bash -c "ffmpeg -hide_banner -stream_loop -1 -re -i ./dev/{vidi_filenammm}.mp4 -c copy -an -f mp4 -movflags cmaf+separate_moof+delay_moov+skip_trailer+frag_every_frame - '
                            f' | RUST_LOG=info ./target/debug/moq-pub --name {track} https://{first_hop_relay[k][0]}:4443 {tls_verify_str}" &')
                    else:
                        if config['mode'] == 'gst':
                            holder = " "
                            if my_debug:
                                holder = " -hold "
                            gst_shark_str = ""
                            if gst_shark>0:
                                gst_shark_str = 'export GST_DEBUG="GST_TRACER:7"; export GST_SHARK_CTF_DISABLE=TRUE; '
                            if gst_shark == 1:
                                gst_shark_str += 'export GST_TRACERS="proctime";'
                            if gst_shark == 2:
                                gst_shark_str += 'export GST_TRACERS="interlatency";'
                            gst_tls_str = ""
                            if not forklift_certified:
                                gst_tls_str = "tls-disable-verify=true"

                            le_cmd = f'xterm {holder} -T "{h.name}-pub" -e bash -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; {gst_shark_str} gst-launch-1.0 -q -v -e filesrc location="./dev/{vidi_filenammm}.mp4"  ! qtdemux name=before01 \
                            before01.video_0 ! h264parse config-interval=-1 name=before02 ! avdec_h264 name=before03 ! videoconvert name=before2 ! timestampoverlay name=middle ! videoconvert name=after1 ! x264enc tune=zerolatency name=after2 ! h264parse name=after3 ! isofmp4mux chunk-duration=1 fragment-duration=1 name=after4 ! moqsink {gst_tls_str} url="https://{first_hop_relay[k][0]}:4443" namespace="{track}" 2> measurements/baseline_{track}_{current_time}_{h.name}.txt ; sleep 3 "&'

                debug(f'issuing on {h} connecting to {first_hop_relay[k][0]}:\n {h} {le_cmd}')
                # if not my_debug:
                h.cmd(le_cmd)
                sleep(the_path.wait_between_pubs)
                k += 1

            # if this is 1.5 or more it will cause problems
            # around 0.7 needed
            sleep(the_path.wait_after_pubs)


            k=0
            for (h,track) in subs:
                filename = f"measurements/{track}_{current_time}_{h.name}"
                errorfile1 = f"measurements/{track}_{current_time}_{h.name}_iferror"
                errorfile2 = f"measurements/{track}_{current_time}_{h.name}_iferror2"
                if config['mode'] in ['clock', 'clockr']:

                    le_cmd = (f'xterm -hold  -T "{h.name}-sub-t" -e bash -c "RUST_LOG=info ./target/debug/moq-clock --namespace {track} https://{last_hop_relay[k][0]}:4443 {tls_verify_str} | tee {filename}.txt" &')
                else:
                    if config['mode'] == 'ffmpeg':
                          le_cmd = (f'xterm -hold -T "{h.name}-sub-t" -e bash  -c "RUST_LOG=info RUST_BACKTRACE=1 ./target/debug/moq-sub --name {track} {tls_verify_str} https://{last_hop_relay[k][0]}:4443 '
                      f' --tls-disable-verify | ffplay -window_title \'{h.name}sub\' -x 360 -y 200 - "&')
                    else:

                        le_sink = "autovideosink"
                        if not video_on:
                            le_sink = "fakesink"

                        le_cmd = f'xterm  -hold  -T "{h.name}-sub-t" -e bash  -c "export GST_PLUGIN_PATH="${{PWD}}/../moq-gst/target/debug${{GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}}:${{PWD}}/../6gxr-latency-clock"; export RUST_LOG=info; ./target/debug/moq-sub --name {track} {tls_verify_str} https://{last_hop_relay[k][0]}:4443 2> {errorfile1}.txt | GST_DEBUG=timeoverlayparse:4 gst-launch-1.0 --no-position filesrc location=/dev/stdin ! decodebin ! videoconvert ! timeoverlayparse ! videoconvert ! {le_sink} 2> {filename}.txt | tee {errorfile2}.txt" &'


                if not my_debug:
                    h.cmd(le_cmd)

                debug(f'issuing on {h} connecting to {last_hop_relay[k][0]}:\n {h} {le_cmd}')
                sleep(the_path.wait_between_subs)
                k += 1

            sleep(1)

            if video_on:

                if config['mode'] == 'gst':
                    sleep(2)
                    try:
                        output = subprocess.check_output(['xdotool', 'search', '--name', 'gst-launch'])
                        process_ids = output.decode().split()
                        for i, process_id in enumerate(process_ids):
                            sleep(0.2)
                            subprocess.call(['xdotool', 'windowmove', process_id, f'{i*max_resolution+50}', '0'])
                    except subprocess.CalledProcessError:
                            print("No windows found with the name 'gst-launch'")
                else:
                    if config['mode'] == 'ffmpeg':
                        for i in range(len(subs)):
                            sleep(0.2)
                            subprocess.call(['xdotool', 'search', '--name', f'h{i}sub', 'windowmove', f'{i*max_resolution+50}', '0'])


            if all_gas_no_brakes and not my_debug:
                sleep(max_video_duration+2)
            else:
                CLI( net )

            sleep(5)

            for (h,_) in subs:
                if config['mode'] == 'gst':
                    h.cmd('pkill -f -TERM  gst-launch')
                h.cmd('pkill -f -TERM  xterm')

            for (h,_) in pubs:
                if config['mode'] == 'gst':
                    h.cmd('pkill -f -TERM gst-launch')
                h.cmd('pkill -f -TERM xterm')
            sleep(1)



            all_network_receive_bytes = 0
            all_network_receive_packets = 0
            all_network_transmit_bytes = 0
            all_network_transmit_packets = 0
            # Count the occurrences of each unique string in the subs list
            number_of_subscribers = Counter(track for _, track in subs)

            for host in net.hosts:
                # TODO this now is be more optimal but should be checked
                if host.name != 'h999':
                    # we need to exec this, because otherwise all of the outputs after starting the host will be displayed for the following command
                    host.cmd("echo clean")
                    interfaces = host.cmd('ip -br a').strip().split('\n')
                    interface_names = []
                    for line in interfaces:
                        parts = line.split()
                        interface_name = parts[0].split('@')[0]
                        ip_address = parts[2] if len(parts) > 2 else ''
                        # we can do this because the connections between relays are on the 10.0.x.x network
                        if '10.0.' in ip_address:
                            interface_names.append(interface_name)
                    net_dev_output = host.cmd('cat /proc/net/dev').strip().split('\n')
                    with open(f"measurements/{current_time}_{host.name}_network.txt", 'w') as file:
                        file.write('\n'.join(net_dev_output))
                        file.write("\n")
                        file.write('\n'.join(interfaces))

                    # publisher side division for multiple subscribers
                    # from the topo we change the divider at the publisher to the number of subscribers of that track
                    # this because after the calc we will multiple by the link length which contains publisher relays
                    # transmitting interfaces already as many times as many subscribers are.
                    divider = 1
                    if config['api'] == 'origi':
                        for track, relay_host in pub_relays.items():
                            if relay_host == host:
                                divider = number_of_subscribers[track]
                                break
                    # we look for the interfaces which are choosen, and sum up only the 9th and 10th column, transmit bytes and packets
                    for line in net_dev_output:
                        if any(interface_name in line for interface_name in interface_names):
                            stats = line.split(':')[1].split()
                            # with our 720p test video around 726-900 bytes or around 20 packets of control info can happen on even inactive interfaces
                            if int(stats[8]) > 1100 and int(stats[9]) > 50:
                                all_network_transmit_bytes += (int(stats[8])/ divider)
                                all_network_transmit_packets += (int(stats[9])/ divider)
                                if divider != 1:
                                   print(f"transmit: {int(stats[8])} / {divider} = {int(stats[8])/ divider}")



            with open(f"measurements/{current_time}_api_network.txt", 'w') as file:
                file.write(api.cmd('cat /proc/net/dev'))
                file.write("\n")
                file.write(api.cmd('ip -br a'))


            sum_cost = {}
            sum_underlay_length = {}

            if config['mode'] in ['clock', 'clockr']:
                for (h, track) in subs:

                    file_path1 = f"measurements/{track}_{current_time}_{h.name}.txt"
                    with open(file_path1, 'r') as file:
                        output = file.read()
                    file_path2 = f"measurements/{track}_{current_time}_{h.name}_clocked.txt"
                    with open(file_path2, 'w') as file:
                        # todo this does nothing
                        counter2 = 0
                        # we leave out the first 5 lines because regardless of the hw resources they are always around 1 second and so spoil the averages
                        for line in output.splitlines():
                            try:
                                number = int(line.strip())
                                if number<1000:
                                    latency = number*1000000
                                    file.write(f"{latency},{counter2}\n")
                            except ValueError:
                                continue

            if config['api'] == 'origi':
                for first_hop_relay in config['first_hop_relay']:
                    first_hop_track = first_hop_relay['track']
                    relevant_last_hop_relays = [item['relayid'] for item in config['last_hop_relay'] if item['track'] == first_hop_track]
                    sum_cost[first_hop_relay['track']] = 0
                    sum_underlay_length[first_hop_relay['track']] = 0
                    for relayid in relevant_last_hop_relays:
                        for edge in config['edges']:
                            if (edge['node1'] == first_hop_relay['relayid'] and edge['node2'] == relayid) or \
                               (edge['node1'] == relayid and edge['node2'] == first_hop_relay['relayid']):
                                sum_cost[first_hop_relay['track']] += edge['attributes']['cost']
                                sum_underlay_length[first_hop_relay['track']] += edge['attributes'].get('underlay_length', 1)
                    all_network_receive_bytes = all_network_receive_bytes*sum_underlay_length[first_hop_relay['track']]
                    all_network_receive_packets = all_network_receive_packets*sum_underlay_length[first_hop_relay['track']]
                    all_network_transmit_bytes = all_network_transmit_bytes*sum_underlay_length[first_hop_relay['track']]
                    all_network_transmit_packets = all_network_transmit_packets*sum_underlay_length[first_hop_relay['track']]

            else:
                number_of_used_links = 0
                if config['api'] == 'opti':
                    sum_cost = {}
                    for first_hop_relay in config['first_hop_relay']:
                        first_hop_track = first_hop_relay['track']
                        sum_cost[first_hop_relay['track']] = 0
                        api.cmd('echo clean')
                        response = api.cmd(f'curl -s http://10.1.1.1:4442/tracks/{first_hop_track}/topology')
                        response_lines = response.strip().split('\n')
                        sanitized_response_lines = [line for line in response_lines if line.startswith('{')][0].strip('(venv)')
                        if len(response_lines) > 1:
                            response_json = json.loads(sanitized_response_lines)
                            number_of_used_links=len(response_json.get('used_links', []))
                            sum_cost[first_hop_relay['track']] += float(response_json.get('cost', 0))



            net.stop()

            if config['mode'] == 'gst':
                for (h,track) in subs:
                    filename = f"measurements/{track}_{current_time}_{h.name}"

                    with open(f"{filename}.txt", 'r') as file:
                                lines = file.readlines()
                                csv_lines = ["Latency,Frame-id\n"]
                                for line in lines:
                                    latency_match = re.search(r'Latency: (\d+)', line)
                                    frame_id_match = re.search(r'Frame-id: (\d+)', line)
                                    if latency_match and frame_id_match:
                                        latency = latency_match.group(1)
                                        frame_id = frame_id_match.group(1)
                                        csv_lines.append(f"{latency},{frame_id}\n")

                    with open(f"{filename}_cleaned.txt", 'w') as file:
                        file.writelines(csv_lines)

            if config['mode'] in ['gst','clock','clockr']:
                # todo this is not useable rightnow
                if gst_shark>0:
                    print("latest_files: ", latest_files)
                    baseline_files = glob.glob(os.path.join(folder_path, 'baseline*'))
                    baseline_file = max(baseline_files, key=os.path.getctime)
                    print("baseline_file: ", baseline_file)
                    if gst_shark==1:
                        baseline=0
                        with open(baseline_file, 'r') as file:
                            for line in file:
                                element_counts = {}
                                element_sums = {}
                                element_avarages={}
                                for line in file:
                                    match = re.search(r'element=\(string\)(\w+), time=\(string\)0:00:00.(\d+)', line)

                                    if match:
                                        element = match.group(1)
                                        if element in element_counts:
                                            element_counts[element] += 1
                                        else:
                                            element_counts[element] = 1
                                        time= int(match.group(2))
                                        if element in element_sums:
                                            element_sums[element] += time
                                        else:
                                            element_sums[element] = time

                                for element, count in element_counts.items():
                                    print(f"Element: {element}, Count: {count}, sum: {element_sums[element]}, av:{element_sums[element]/count}")
                                    element_avarages[element]=element_sums[element]/count
                            element_avarages.pop('middle')
                            baselines = [value for key, value in element_avarages.items() if key.startswith('after')]
                            baseline = sum(baselines)/1e9
                    else:
                        if gst_shark==2:
                            baseline=0
                            baseline_plus = []
                            baseline_minus = []
                            with open(baseline_file, 'r') as file:
                                with open('test.txt', 'w') as test_file:
                                    for line in file:
                                        match = re.search(r'filesrc0_src, to_pad=\(string\)moqsink0_sink, time=\(string\)0:00:00\.(\d+);', line)
                                        if match:
                                            baseline_plus.append(int(match.group(1)))

                                        match = re.search(r'filesrc0_src, to_pad=\(string\)middle_src, time=\(string\)0:00:00\.(\d+);', line)
                                        if match:
                                            baseline_minus.append(int(match.group(1)))

                                baseline = (sum(baseline_plus) / len(baseline_plus)) / 1e9 - (sum(baseline_minus) / len(baseline_minus)) / 1e9


                latencies = []



                summing_current_time = datetime.datetime.now().strftime("%m%d%H")

                file_exists = os.path.isfile(f"measurements/enddelays_{summing_current_time}.txt")

                end_of_file_part = "cleaned"
                if config['mode'] == 'gst':
                    end_of_file_part = "cleaned"
                else:
                    if config['mode'] in ['clock', 'clockr']:
                        end_of_file_part = "clocked"



                with open(f"measurements/enddelays_{summing_current_time}.txt", 'a') as enddelays_file:
                    header = f"meas. time;track__host;topo;api;average of timestamps;deviation of timestamps;baseline;avarage-baseline;number of frames;ending time;sum cost for all subs on track;tx bytes for all;tx pckts for all"
                    if not file_exists:
                        enddelays_file.write(f"\n{header}")
                        print(f"{header}")
                    clock_str=""
                    if config['mode'] in ['clock', 'clockr']:
                        clock_str = f"-{config['mode']}"
                    enddelays_file.write(f"\n---")
                    print(f"{config['mode']}-{config['api']}-{topofile}")
                    for (h,track) in subs:
                        file_path = f"measurements/{track}_{current_time}_{h.name}"
                        with open(f"{file_path}_{end_of_file_part}.txt", 'r') as file:
                            file_latencies = []
                            count = 0
                            last_frame = 1

                            for line in file:
                               latency = extract_latency(line)
                               if latency is not None:
                                   file_latencies.append(latency)
                                   count += 1
                                   last_frame = line.split(",")[1]

                        if file_latencies:
                            average, distribution, median, percentile_99 = calculate_statistics(file_latencies)
                            did_it_warn = False
                            ending_time = None
                            if config['mode'] == 'gst':
                                error_filename = f"{file_path}_iferror.txt"
                                with open(error_filename, 'r') as error_file:
                                    for line in error_file:
                                        if 'WARN' in line:
                                            did_it_warn = True
                                error_filename2 = f"{file_path}_iferror2.txt"
                                with open(error_filename2, 'r') as error_file2:
                                    for line2 in error_file2:
                                        match = re.search(r'Execution ended after ([0-9:.]+)', line2)
                                        if match:
                                            ending_time = match.group(1)
                                            break
                            else:
                                ending_time = 0
                                did_it_warn = 0
                            file_name_parts = file_path.replace('measurements/', '').split('_')
                            a = file_name_parts[-2]
                            b = '_'.join(file_name_parts[:-2]) + '__' + file_name_parts[-1]
                            actual_line = f"{a};{clock_str}{b};{topofile.replace('.yaml','')};{config['api']};{average};{distribution};{based_line};{average-based_line};{count};{ending_time};{sum_cost[track]};{all_network_transmit_bytes};{all_network_transmit_packets}"
                            enddelays_file.write(f"\n{actual_line}")
                            print(f"{actual_line}")
                            if gst_shark == 2:
                                enddelays_file.write(f">> subtracting average interlatency: {average-baseline}\n")
                            if gst_shark == 1:
                                enddelays_file.write(f">> subtracting average proctimes: {average-baseline}\n")
                        if gst_shark == 2:
                            print(f">> subtracting average interlatency: {average-baseline}")
                        if gst_shark == 1:
                            print(f">> subtracting average proctimes: {average-baseline}")

# Change ownership of all files in the measurements directory
subprocess.call(['sudo', 'chown', '-R', f'{the_path.user}:{the_path.user}', 'measurements'])

