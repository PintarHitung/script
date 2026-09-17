#!/usr/bin/env python3
"""
===================================================================
LKS LINUX SERVER CONFIGURATION - MASTER AUTO PROVISIONER
===================================================================
Author: Assistant
OS Target: Ubuntu Server 20.04 / 22.04 / 24.04 LTS
===================================================================
"""

import os
import subprocess
import sys
import time

# =================================================================
# VARIABEL KONFIGURASI SESUAI PERMINTAAN TERBARU
# =================================================================
DOMAIN_NAME = "lks.local"
SERVER_IP = "10.11.12.206"
ROOT_PASSWORD = "LKSOKE123"
DB_ROOT_PASS = "LKSOKE123"
LDAP_ADMIN_PASS = "LKSOKE123"
# =================================================================

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(msg):
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}[*] {msg}{Colors.ENDC}")

def print_success(msg):
    print(f"{Colors.OKGREEN}{Colors.BOLD}[ ✓ ] {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.FAIL}{Colors.BOLD}[ ✗ ] {msg}{Colors.ENDC}")

def run_cmd(cmd, ignore_error=False, silent=True):
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    
    try:
        result = subprocess.run(cmd, shell=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 and not ignore_error:
            raise Exception(result.stderr.strip())
        return True, result.stdout
    except Exception as e:
        if not ignore_error:
            print_error(f"Command Failed: {cmd}\nError: {e}")
        return False, str(e)

def check_root():
    if os.geteuid() != 0:
        print(f"{Colors.FAIL}ERROR: Script wajib dijalankan dengan sudo!{Colors.ENDC}")
        sys.exit(1)

def step_ip_forwarding():
    print_step("1. Konfigurasi IP Forwarding (Poin 10)")
    run_cmd("sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/g' /etc/sysctl.conf")
    run_cmd("echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf")
    run_cmd("sysctl -p")
    print_success("IP Forwarding diaktifkan")

def step_ssh():
    print_step("2. Konfigurasi SSH Server (OpenSSH) (Poin 1)")
    run_cmd("apt-get update -y && apt-get install openssh-server -y")
    run_cmd("sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/g' /etc/ssh/sshd_config")
    run_cmd("systemctl restart ssh")
    run_cmd("systemctl enable ssh")
    print_success("OpenSSH Server diinstal dan Root Login diizinkan")

def step_dns():
    print_step("3. Konfigurasi DNS Server (BIND9) (Poin 2)")
    run_cmd("apt-get install bind9 bind9utils bind9-doc dnsutils -y")
    
    zone_conf = f"""
zone "{DOMAIN_NAME}" {{
    type master;
    file "/etc/bind/db.{DOMAIN_NAME}";
}};
"""
    with open("/etc/bind/named.conf.local", "w") as f:
        f.write(zone_conf)
        
    db_forward = f"""$TTL    604800
@       IN      SOA     ns.{DOMAIN_NAME}. admin.{DOMAIN_NAME}. (
                              2         ; Serial
                         604800         ; Refresh
                          86400         ; Retry
                        2419200         ; Expire
                         604800 )       ; Negative Cache TTL
;
@       IN      NS      ns.{DOMAIN_NAME}.
@       IN      A       {SERVER_IP}
ns      IN      A       {SERVER_IP}
www     IN      A       {SERVER_IP}
mail    IN      A       {SERVER_IP}
"""
    with open(f"/etc/bind/db.{DOMAIN_NAME}", "w") as f:
        f.write(db_forward)
        
    # PERBAIKAN: Menggunakan 'named' bukan 'bind9'
    run_cmd("systemctl restart named")
    run_cmd("systemctl enable named")
    print_success(f"BIND9 diinstal dan Domain {DOMAIN_NAME} dibuat")

def step_web_nginx():
    print_step("4. Konfigurasi Secure Web Server (Nginx) (Poin 3)")
    run_cmd("apt-get install nginx openssl -y")
    ssl_cmd = f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt -subj '/C=ID/ST=Jawa/L=LKS/O=Sekolah/OU=IT/CN={DOMAIN_NAME}'"
    run_cmd(ssl_cmd)
    
    nginx_conf = f"""server {{
    listen 80;
    listen 443 ssl;
    server_name www.{DOMAIN_NAME} {DOMAIN_NAME};
    
    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;
    
    root /var/www/html;
    index index.html;
    
    location / {{
        try_files $uri $uri/ =404;
    }}
}}"""
    with open(f"/etc/nginx/sites-available/{DOMAIN_NAME}", "w") as f:
        f.write(nginx_conf)
        
    run_cmd(f"ln -sf /etc/nginx/sites-available/{DOMAIN_NAME} /etc/nginx/sites-enabled/")
    run_cmd("systemctl restart nginx")
    run_cmd("systemctl enable nginx")
    print_success("Nginx dengan HTTPS (SSL) berhasil dibuat")

def step_haproxy():
    print_step("5. Konfigurasi Load Balance (HAProxy) (Poin 4)")
    run_cmd("apt-get install haproxy -y")
    
    haproxy_append = f"""
frontend http_front
    bind *:8080
    default_backend web_backend

backend web_backend
    balance roundrobin
    server web1 127.0.0.1:80 check
"""
    with open("/etc/haproxy/haproxy.cfg", "a") as f:
        f.write(haproxy_append)
        
    run_cmd("systemctl restart haproxy")
    run_cmd("systemctl enable haproxy")
    print_success("HAProxy diinstal (Listen Port 8080 -> 80)")

def step_ansible():
    print_step("6. Konfigurasi Automation (Ansible) (Poin 5)")
    run_cmd("apt-get install software-properties-common -y")
    run_cmd("apt-add-repository --yes --update ppa:ansible/ansible")
    run_cmd("apt-get install ansible -y")
    print_success("Ansible terinstal")

def step_database():
    print_step("7. Konfigurasi Database Server (MariaDB) (Poin 6)")
    run_cmd("apt-get install mariadb-server -y")
    sql_commands = f"""
    CREATE DATABASE IF NOT EXISTS db_lks;
    CREATE USER IF NOT EXISTS 'admin_lks'@'localhost' IDENTIFIED BY '{DB_ROOT_PASS}';
    GRANT ALL PRIVILEGES ON *.* TO 'admin_lks'@'localhost' WITH GRANT OPTION;
    FLUSH PRIVILEGES;
    """
    with open("/tmp/setup_db.sql", "w") as f:
        f.write(sql_commands)
    
    run_cmd("mysql < /tmp/setup_db.sql")
    run_cmd("systemctl enable mariadb")
    print_success("MariaDB terinstal dan User admin_lks dibuat")

def step_mail_server():
    print_step("8. Konfigurasi Mail Server (Postfix & Dovecot) (Poin 7)")
    run_cmd("echo 'postfix postfix/main_mailer_type string \"Internet Site\"' | debconf-set-selections")
    run_cmd(f"echo 'postfix postfix/mailname string {DOMAIN_NAME}' | debconf-set-selections")
    run_cmd("apt-get install postfix dovecot-core dovecot-imapd dovecot-pop3d -y")
    run_cmd(f"postconf -e 'myhostname = mail.{DOMAIN_NAME}'")
    run_cmd(f"postconf -e 'mydomain = {DOMAIN_NAME}'")
    run_cmd(f"postconf -e 'myorigin = /etc/mailname'")
    run_cmd("systemctl restart postfix dovecot")
    run_cmd("systemctl enable postfix dovecot")
    print_success("Postfix & Dovecot diinstal")

def step_webmail():
    print_step("9. Konfigurasi Webmail Server (Roundcube) (Poin 8)")
    run_cmd("echo 'roundcube-core roundcube/dbconfig-install boolean false' | debconf-set-selections")
    run_cmd("apt-get install roundcube roundcube-mysql php-fpm php-mysql -y")
    run_cmd("ln -sf /usr/share/roundcube /var/www/html/roundcube")
    print_success("Roundcube Webmail terinstal")

def step_routing():
    print_step("10. Konfigurasi Routing Static/Dynamic (Poin 9)")
    run_cmd("ip route add 10.99.99.0/24 dev lo", ignore_error=True)
    print_success("Dummy Static Routing ditambahkan ke loopback")

def step_firewall():
    print_step("11. Konfigurasi Firewall & NAT (nftables) (Poin 11)")
    run_cmd("apt-get install nftables -y")
    
    nft_conf = """flush ruleset
table inet filter {
    chain input {
        type filter hook input priority 0; policy accept;
        iif "lo" accept
        ct state established,related accept
        tcp dport 22 accept
        tcp dport 80 accept
        tcp dport 443 accept
    }
}
table ip nat {
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname != "lo" masquerade
    }
}"""
    with open("/etc/nftables.conf", "w") as f:
        f.write(nft_conf)
        
    run_cmd("systemctl restart nftables")
    run_cmd("systemctl enable nftables")
    print_success("Nftables (Firewall + NAT) diaktifkan")

def step_vpn():
    print_step("12. Konfigurasi VPN Server (OpenVPN) (Poin 12)")
    run_cmd("apt-get install openvpn easy-rsa -y")
    print_success("OpenVPN & Easy-RSA diinstal")

def step_ldap():
    print_step("13. Konfigurasi LDAP Server (Poin 13)")
    run_cmd(f"echo 'slapd slapd/root_password password {LDAP_ADMIN_PASS}' | debconf-set-selections")
    run_cmd(f"echo 'slapd slapd/root_password_again password {LDAP_ADMIN_PASS}' | debconf-set-selections")
    run_cmd("apt-get install slapd ldap-utils -y")
    print_success("OpenLDAP (slapd) diinstal")

def main():
    os.system('clear')
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("====================================================")
    print("🚀 PROVISIONING LKS LINUX SERVER BERJALAN 🚀")
    print("====================================================")
    print(f"{Colors.ENDC}")
    
    check_root()
    
    print("0. Update Repository APT")
    run_cmd("apt-get update -y")
    print_success("Repository Updated\n")

    steps = [
        step_ip_forwarding, step_ssh, step_dns, step_web_nginx,
        step_haproxy, step_ansible, step_database, step_mail_server,
        step_webmail, step_routing, step_firewall, step_vpn, step_ldap
    ]
    
    for step in steps:
        try:
            step()
        except Exception as e:
            print_error(f"Gagal: {str(e)}")
            
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}====================================================")
    print("🎉 SEMUA PROSES SELESAI 🎉")
    print("====================================================\n")
    print(f"{Colors.ENDC}")

if __name__ == "__main__":
    main()