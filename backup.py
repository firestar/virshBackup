import os
import re
from datetime import datetime

def local_command(command):
    #print "\t{ "+command + " } "
    stream = os.popen(command)
    output = stream.read()
    return output

def remote_command(command):
    #print "\t{ "+command + " } "
    stream = os.popen('ssh '+HOST+' "'+command+'"')
    output = stream.read()
    return output

HOST = "root@10.0.0.21";
DIRECTORY = "/a/backups/"
TEMP_DIRECTORY = "/temp/"

VM_LIST = remote_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf list --name').split("\n")
for VM in VM_LIST:
    if VM != "" and VM != "HostedEngine":
        current_timestamp = datetime.now().strftime("%Y-%j.%H%M%S")
        path_to_backup = DIRECTORY + VM + "/" + current_timestamp + "/"

        disks = []

        print "Backing up " + VM + " at " + current_timestamp + " and saving to " + path_to_backup
        local_command('mkdir -p ' + path_to_backup)
        remote_command('mkdir -p ' + TEMP_DIRECTORY)
        print "Created save path."
        #print shell_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf dominfo '+VM)
        print "Creating xml file with configuration."
        f = open(path_to_backup+"vm.xml", "w")
        xml_data = remote_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf dumpxml '+VM)
        f.write(xml_data)
        f.close()
        blocks=remote_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf domblklist '+VM+' --details').split("\n")
        for x in range(1, len(blocks)-1):
            items = blocks[x].split()
            if len(items) == 4 and items[1]=='disk':
                qemu_info_list=remote_command('qemu-img info '+items[3]).split("\n")
                qemu = {}
                for qemu_info in qemu_info_list:
                    match = re.search("([a-zA-Z ]+): (.*)", qemu_info)
                    if match:
                        qemu[match.group(1)] = match.group(2)

                if qemu.has_key('file format'):
                    disk_information = {
                        "dev": items[2],
                        "path": items[3],
                        "type": qemu['file format']
                    }
                    disks.append(disk_information)
                else:
                    print "Error qemu info check failed."
        driver_string = []
        for disk in disks:
            driver_string.append('--diskspec '+disk['dev']+',driver=qcow2,file='+TEMP_DIRECTORY+VM+'-'+disk['dev']+'.cow')

        # Create snapshot disks
        print "Creating snapshot."
        result_of_snapshot = remote_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf snapshot-create-as '+VM+' --no-metadata --disk-only --atomic '+" ".join(driver_string))
        if re.search("created", result_of_snapshot):
            print "Snapshot created."
            # Convert all disks to QCOW2 images
            print "Converting images to qcow2"
            for disk in disks:
                print "Converting "+disk['dev']+" to qcow2"
                print remote_command('qemu-img convert -f raw -O qcow2 '+disk['path']+' '+TEMP_DIRECTORY+VM+'-'+disk['dev']+'-base.cow')

            # Pivot all disks back to their base
            for disk in disks:
                print "Pivoting back "+disk['dev']+" to base image"
                result_of_pivot = remote_command('virsh -c qemu:///system?authfile=/etc/ovirt-hosted-engine/virsh_auth.conf blockcommit '+VM+' '+disk['dev']+' --active --verbose --pivot')
                if re.search("Successfully pivoted", result_of_pivot):
                    print result_of_pivot
                    print remote_command('rm -f '+TEMP_DIRECTORY+VM+'-'+disk['dev']+'.cow')
                else:
                    print result_of_pivot

            # Transfer all backed up base images to backup directory
            for disk in disks:
                print "Downloading "+VM+'-'+disk['dev']+'-base.cow'
                print local_command('scp '+HOST+':'+TEMP_DIRECTORY+VM+'-'+disk['dev']+'-base.cow '+path_to_backup+VM+'-'+disk['dev']+'.cow')
                print remote_command('rm -f '+TEMP_DIRECTORY+VM+'-'+disk['dev']+'-base.cow')

            print "Completed Backup of "+VM
        else:
            print "Failed to create snapshot."
       
        print ""
        print ""
