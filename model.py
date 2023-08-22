import json
import paramiko
import time


class SSHOperations:

    def __init__(self, ip_domain, port, username, password):
        # Create a new SSH self.client
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the server
        try:
            self.client.connect(ip_domain, port=int(port), username=username, password=password)
            print('Successfully connected to the server\n')
            self.connection = True

        except Exception as e:
            print(f'Failed to connect to the server, please check your information and try again\nError: {str(e)}\n')
            self.connection = False

    def update_server(self):
        print("updating server, it may take a couple of minutes ...")
        self.client.exec_command("sudo killall apt apt-get")
        self.client.exec_command("sudo dpkg --configure -a")
        stdin, stdout, stderr = self.client.exec_command("apt-get update && sudo apt-get upgrade -y")
        errors = stderr.read().decode()
        if errors:
            print(f'Error updating server')
            return
        print("server updated successfully")

    def add_user(self):
        with open('info.json', 'r') as f:
            users_info = json.load(f)["users"]

        def _add_user(user_info):
            # Create new user
            stdin, stdout, stderr = self.client.exec_command(
                'sudo useradd -s /usr/sbin/nologin {}'.format(user_info['username']))
            errors = stderr.read().decode()
            if errors:
                print(f'Error creating user: {errors}\n')
                return

            # Set user password
            stdin, stdout, stderr = self.client.exec_command(
                'echo "{}:{}" | sudo chpasswd'.format(user_info['username'], user_info['password']))
            errors = stderr.read().decode()
            if errors:
                print(f'Error setting user password: {errors}\n')
                return

            print('Successfully created user {}\n'.format(user_info['username']))

        for user in users_info:
            try:
                _add_user(user)

            except Exception as exc:
                print('Error creating user {}\n{}\n'.format(user['username'], exc))

        print('Successfully created all users\n')

    def change_ssh_port(self):
        # Ask the user for the new SSH port
        new_ssh_port = 2095
        # Create a temporary copy of the sshd_config file
        backup_command = "sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak"
        stdin, stdout, stderr = self.client.exec_command(backup_command)

        # Modify the SSH port in the temporary copy of sshd_config
        modify_command = f"sudo sed -i 's/#Port .*/Port {new_ssh_port}/' /etc/ssh/sshd_config.bak"
        stdin, stdout, stderr = self.client.exec_command(modify_command)

        # Replace the original sshd_config file with the modified one
        replace_command = "sudo mv /etc/ssh/sshd_config.bak /etc/ssh/sshd_config"
        stdin, stdout, stderr = self.client.exec_command(replace_command)

        # Restart the SSH service to apply the changes
        restart_command = "sudo service ssh restart"
        stdin, stdout, stderr = self.client.exec_command(restart_command)

        print(f'SSH port has been changed to {new_ssh_port}. Please reconnect to the server.\n')

    def setup_udpgw(self):
        # Check if 'screen' package is installed
        command = 'dpkg -s screen'
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode().strip()
        if errors:
            # If 'screen' is not installed, install it
            command = 'sudo apt-get install -y screen'
            stdin, stdout, stderr = self.client.exec_command(command)
            errors = stderr.read().decode().strip()
            if errors:  # Check if a real error occurred
                print(f'Error executing command "{command}": {errors}\n')
                return
            else:
                print('Screen installed successfully\n')

        # Ask the user for the UDPGW port
        udpgw_port = 7302

        # Kill any processes using the file
        command = 'pkill -f /usr/bin/badvpn-udpgw'
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode()
        if errors:  # Check if a real error occurred
            print(f'Error executing command "{command}": {errors}\n')
            return

        # Check if the file exists
        command = 'ls /usr/bin/badvpn-udpgw'
        stdin, stdout, stderr = self.client.exec_command(command)
        file_exists = stdout.read().decode().strip()

        # If the file doesn't exist, download it
        if not file_exists:
            command = 'wget -O /usr/bin/badvpn-udpgw "https://raw.githubusercontent.com/daybreakersx/premscript/master/badvpn-udpgw64"'
            stdin, stdout, stderr = self.client.exec_command(command)
            errors = stderr.read().decode()
            if "Saving to" not in errors:  # Check if a real error occurred
                print(f'Error executing command "{command}": {errors}\n')
                return

        # Wait for the file to download
        time.sleep(8)

        # Create the rc.local file if it doesn't exist
        command = 'touch /etc/rc.local'
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode()
        if errors:  # Check if a real error occurred
            print(f'Error executing command "{command}": {errors}\n')
            return

        # Create and edit the rc.local file
        rc_local_commands = [
            "#!/bin/sh -e",
            f"screen -AmdS badvpn badvpn-udpgw --listen-addr 127.0.0.1:{udpgw_port}",
            "exit 0",
        ]
        rc_local_content = "\n".join(rc_local_commands)

        # Write the content to the rc.local file
        command = f'echo "{rc_local_content}" > /etc/rc.local'
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode()
        if errors:
            print(f'Error executing command "{command}": {errors}\n')
            return

        # Run the final command
        command = f"chmod +x /etc/rc.local && chmod +x /usr/bin/badvpn-udpgw && systemctl daemon-reload && sleep 0.5 && systemctl start rc-local.service && screen -AmdS badvpn badvpn-udpgw --listen-addr 127.0.0.1:{udpgw_port}"
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode()
        if errors:
            print(f'Error executing command "{command}": {errors}\n')
            return

        print('UDPGW setup successful\n')

    def install_nginx(self):
        # Always assume the operating system is Debian
        command = 'sudo DEBIAN_FRONTEND=noninteractive apt-get install nginx -y'

        # Execute the installation command
        stdin, stdout, stderr = self.client.exec_command(command)
        errors = stderr.read().decode()
        if errors:
            print(f'Error installing nginx: {errors}\n')
            return

        print('Nginx installation successful\n')

    def install_certbot_and_get_ssl(self, domain):
        command = 'sudo DEBIAN_FRONTEND=noninteractive apt install certbot python3-certbot-nginx -y'
        print(f"Running command: {command}\n")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(out)
        print(err)
        time.sleep(20)  # wait for 20 seconds

        command = f'sudo DEBIAN_FRONTEND=noninteractive certbot --nginx -d {domain} --register-unsafely-without-email --agree-tos'
        print(f"Running command: {command}\n")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(out)
        print(err)

    def close_connection(self):
        self.client.close()


if __name__ == "__main__":
    # Getting the credentials
    with open('info.json', 'r') as f:
        server_info = json.load(f)['server']
    conn = SSHOperations(server_info["ip_domain"], server_info["port"], server_info["username"], server_info["password"])
    del server_info
    # Operations
    conn.update_server()
    conn.add_user()
    conn.change_ssh_port()
    conn.setup_udpgw()
    conn.install_nginx()
    if input("Did you setup your CDN? (y/n) :") == "y":
        conn.install_certbot_and_get_ssl(server_info["domain"])
    conn.close_connection()
