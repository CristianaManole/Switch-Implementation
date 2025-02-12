#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec(dict_port, interfaces):
    while True:
        if own_bridge_ID == root_bridge_ID:
            BPDU = create_BPDU(own_bridge_ID, 0, own_bridge_ID)
            for i in interfaces:
                if dict_port[get_interface_name(i)] == 'T':
                    send_to_link(i, len(BPDU), BPDU) 
        # TODO Send BDPU every second if necessary
        time.sleep(1)

def is_unicast(dest_mac):
    if dest_mac[1] in '02468ace' and dest_mac[0:2] != 'ff':
        return True
    else:
        return False
    
def content_dict(content_sw):
    lines = content_sw.split('\n')
    dict_port = {}
    for i in range(1, len(lines)-1):
        date = lines[i].split()
        dict_port[date[0]] = date[1]
    priority = int(lines[0])
    return dict_port, priority

def create_BPDU(root_bridge_id, root_path_cost, bridge_id):
    dest_mac = bytes([0x01, 0x80, 0xc2, 0x00, 0x00, 0x00])
    BPDU = dest_mac
    BPDU = BPDU + get_switch_mac()
    BPDU = BPDU + struct.pack('!H', 38)
    BPDU = BPDU + struct.pack('!B', 0x42)
    BPDU = BPDU + struct.pack('!B', 0x42)
    BPDU = BPDU + struct.pack('!B', 0x03)
    BPDU = BPDU + struct.pack('!I', 0)
    BPDU = BPDU + struct.pack('!B', 0)
    BPDU = BPDU + struct.pack('!Q', root_bridge_id)
    BPDU = BPDU + struct.pack('!I', root_path_cost)
    BPDU = BPDU + struct.pack('!Q', bridge_id)
    BPDU = BPDU + struct.pack('!H', 0)
    BPDU = BPDU + struct.pack('!H', 0)
    BPDU = BPDU + struct.pack('!H', 0)
    BPDU = BPDU + struct.pack('!H', 0)
    BPDU = BPDU + struct.pack('!H', 0)
    return BPDU


def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    MAC_Table = {}
    switch_id = sys.argv[1]

    cale_sw = 'configs/switch' + str(switch_id) + '.cfg'
    f = open(cale_sw, 'r')
    content_sw = f.read()
    dict_port, priority = content_dict(content_sw) 
    f.close()
    
    #initialization stp
    cp_dict_port = {}
    for i in dict_port:
        cp_dict_port[i] = dict_port[i]

    for i in cp_dict_port:
        if cp_dict_port[i] == 'T':
            cp_dict_port[i] = "blocking"

    global own_bridge_ID
    global root_bridge_ID
    own_bridge_ID = priority
    root_bridge_ID = own_bridge_ID
    last_root_bridge = root_bridge_ID
    root_path_cost = 0

    if own_bridge_ID == root_bridge_ID:
        for i in cp_dict_port:
            cp_dict_port[i] = "designated"

    ####
    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec, args = (dict_port, interfaces))
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    root_port = 999999999

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        dest_mac_cp = dest_mac
        multicast = bytes([0x01, 0x80, 0xc2, 0x00, 0x00, 0x00])
        

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]
        
        

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        # TODO: Implement forwarding with learning
        MAC_Table[src_mac] = interface

        if dest_mac_cp == multicast:
            BPDU_root_bridge_ID = struct.unpack('!Q', data[22:30])[0]
            BPDU_sender_path_cost = struct.unpack('!I', data[30:34])[0]
            BPDU_sender_bridge_ID = struct.unpack('!Q', data[34:42])[0]
            if BPDU_root_bridge_ID < root_bridge_ID:
                root_bridge_ID = BPDU_root_bridge_ID
                root_path_cost = BPDU_sender_path_cost + 10
                root_port = interface

                if last_root_bridge == own_bridge_ID:
                    for i in interfaces:
                        if dict_port[get_interface_name(i)] == 'T' and i != root_port:
                            cp_dict_port[get_interface_name(i)] = "blocking"
                        last_root_bridge = root_bridge_ID
                
                if cp_dict_port[get_interface_name(root_port)] == "blocking":
                    cp_dict_port[get_interface_name(root_port)] = "designated"

                for i in interfaces:
                    if cp_dict_port[get_interface_name(i)] == 'T' and i != root_port:
                        BPDU = create_BPDU(root_bridge_ID, root_path_cost, own_bridge_ID)
                        send_to_link(i, len(BPDU), BPDU)

            elif BPDU_root_bridge_ID == root_bridge_ID:
                if interface == root_port and BPDU_sender_path_cost + 10 < root_path_cost:
                    root_path_cost = BPDU_sender_path_cost + 10
                elif interface != root_port:
                    if BPDU_sender_path_cost > root_path_cost:
                        if cp_dict_port[get_interface_name(interface)] != "designated":
                            cp_dict_port[get_interface_name(interface)] = "designated"
            
            elif BPDU_sender_bridge_ID == own_bridge_ID:
                cp_dict_port[get_interface_name(interface)] = "blocking"
            
            if own_bridge_ID == root_bridge_ID:
                for i in interfaces:
                    cp_dict_port[get_interface_name(i)] = "designated"

        elif is_unicast(dest_mac):
            if dest_mac in MAC_Table:
                if vlan_id != -1:
                    if dict_port[get_interface_name(MAC_Table[dest_mac])] == 'T' and cp_dict_port[get_interface_name(MAC_Table[dest_mac])] != "blocking":
                         send_to_link(MAC_Table[dest_mac], length, data)
                    elif dict_port[get_interface_name(MAC_Table[dest_mac])] == str(vlan_id) and cp_dict_port[get_interface_name(MAC_Table[dest_mac])] != "blocking":
                        tagged_frame = data[0:12] + data[16:]
                        length = length - 4
                        send_to_link(MAC_Table[dest_mac], length, tagged_frame)
                else:
                    if dict_port[get_interface_name(MAC_Table[dest_mac])] == 'T' and cp_dict_port[get_interface_name(MAC_Table[dest_mac])] != "blocking":
                        tagged_frame = data[0:12] + create_vlan_tag(int(dict_port[get_interface_name(interface)])) + data[12:]
                        length = length + 4
                        send_to_link(MAC_Table[dest_mac], length, tagged_frame)
                    elif dict_port[get_interface_name(MAC_Table[dest_mac])] == dict_port[get_interface_name(interface)] and cp_dict_port[get_interface_name(MAC_Table[dest_mac])] != "blocking":
                        send_to_link(MAC_Table[dest_mac], length, data)    
            else:
                for i in interfaces:
                    l = length
                    if i != interface:
                        if vlan_id != -1:
                            if dict_port[get_interface_name(i)] == 'T' and cp_dict_port[get_interface_name(i)] != 'blocking':
                                send_to_link(i, l, data)
                            elif dict_port[get_interface_name(i)] == str(vlan_id) and cp_dict_port[get_interface_name(i)] != 'blocking':
                                tagged_frame = data[0:12] + data[16:]
                                l = l - 4
                                send_to_link(i, l, tagged_frame)
                        else:
                            if dict_port[get_interface_name(i)] == 'T' and cp_dict_port[get_interface_name(i)] != 'blocking':
                                tagged_frame = data[0:12] + create_vlan_tag(int(dict_port[get_interface_name(interface)])) + data[12:]
                                l = l + 4
                                send_to_link(i, l, tagged_frame)
                            elif dict_port[get_interface_name(i)] == dict_port[get_interface_name(interface)] and cp_dict_port[get_interface_name(i)] != 'blocking':
                                send_to_link(i, l, data)         
        else: 
            for i in interfaces:
                l = length
                if i != interface:
                    if vlan_id != -1:
                        if dict_port[get_interface_name(i)] == 'T' and cp_dict_port[get_interface_name(i)] != 'blocking':
                            send_to_link(i, l, data)
                        elif dict_port[get_interface_name(i)] == str(vlan_id) and cp_dict_port[get_interface_name(i)] != 'blocking':
                            tagged_frame = data[0:12] + data[16:]
                            l = l - 4
                            send_to_link(i, l, tagged_frame)
                    else:
                        if dict_port[get_interface_name(i)] == 'T' and cp_dict_port[get_interface_name(i)] != 'blocking':
                            tagged_frame = data[0:12] + create_vlan_tag(int(dict_port[get_interface_name(interface)])) + data[12:]
                            l = l + 4
                            send_to_link(i, l, tagged_frame)
                        elif dict_port[get_interface_name(i)] == dict_port[get_interface_name(interface)] and cp_dict_port[get_interface_name(i)] != 'blocking':
                            send_to_link(i, l, data)  
            
        # TODO: Implement VLAN support
        # TODO: Implement STP support

        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
