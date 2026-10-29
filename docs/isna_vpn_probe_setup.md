# ИСНА / Smart Bridge: read-only VPN probe, no production deploy

**Scope:** TEST application can confirm gateway TCP + HTTP GET from the existing
VPN host `47167` (source `195.49.215.49`). No tax documents, EDS, SOAP POST,
proxy or arbitrary HTTP requests traverse the SSH link. All code changes stay
on branch `test`. No production web app, database or production Git branch
needs to change.

**Current stage:** repository code is ready. The SSH trust/key exchange below
has to be configured by an administrator on *both* VPS. Until then the Android
app still measures TCP directly from TEST VPS and reports it honestly.

## 1. VPN host 47167 (the one with working StrongSwan)

First verify the VPN is up and the fixed probe can reach the gateway:

```bash
sudo ipsec statusall | grep -A 6 nika-smartbridge-test
nc -vz -s 195.49.215.49 -w 8 195.12.113.7 80
```

Install only the fixed read-only probe (standalone Python standard library;
does not install or restart Nika on the VPN host):

```bash
curl -fsSL https://raw.githubusercontent.com/OlegSelamov/nika-crm/test/scripts/isna_gateway_probe.py -o /tmp/nika-isna-gateway-probe.py
python3 -m py_compile /tmp/nika-isna-gateway-probe.py
sudo install -d -m 755 -o root -g root /opt/nika-isna
sudo install -m 755 -o root -g root /tmp/nika-isna-gateway-probe.py /opt/nika-isna/gateway_probe.py
python3 /opt/nika-isna/gateway_probe.py
```

Expected: one JSON record with `"schema":1`, `"tcpOk":true` and, if
the WSDL URL returns 200, `"httpOk":true,"httpStatus":200`.

Create the restricted account (one-time):

```bash
id isna-probe >/dev/null 2>&1 || sudo useradd -m -s /bin/sh isna-probe
sudo install -d -m 700 -o isna-probe -g isna-probe /home/isna-probe/.ssh
```

Get the public SSH host fingerprint **on this trusted VPN host**:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Later, install a *dedicated new* TEST VPS SSH **public** key into
`/home/isna-probe/.ssh/authorized_keys` with a prefix like this:

```text
from="TEST_VPS_PUBLIC_IP",restrict,command="/usr/bin/python3 /opt/nika-isna/gateway_probe.py" ssh-ed25519 AAAA... nika-isna-diagnostic
```

Replace `TEST_VPS_PUBLIC_IP` with the **actual TEST VPS outbound IPv4** and
`AAAA...` with the public key generated in step 2. Do not insert a private
key or password. Set owner `isna-probe:isna-probe` and file mode `600`.
The `restrict` option disables forwarding, PTY and other SSH features; the
forced command ignores any command supplied by the remote client.
**Do not** give this account sudo, a shell login password or access to Nika's
production database.

## 2. TEST VPS (separate test.nikabusiness.com server)

Check which user runs Gunicorn; if blank, systemd defaults to root:

```bash
SERVICE_USER="$(sudo systemctl show -p User --value nika-business-test)"
SERVICE_USER="${SERVICE_USER:-root}"
echo "Test service user: $SERVICE_USER"
```

Make a separate SSH key and trusted-host file readable only by that service:

```bash
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
sudo install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" /etc/nika-isna
sudo -u "$SERVICE_USER" ssh-keygen -q -t ed25519 -N '' -f /etc/nika-isna/probe_id_ed25519 -C nika-isna-diagnostic
sudo cat /etc/nika-isna/probe_id_ed25519.pub
```

Copy **only that public key** to the restricted account on VPN host as
described in step 1.

Pin the VPN host's host key. **Before trusting it**, compare the fingerprint
returned by the following command against the one retrieved locally on VPN
host in step 1; `ssh-keyscan` on its own does *not* authenticate the host:

```bash
ssh-keyscan -t ed25519 195.49.215.49 | ssh-keygen -lf -
ssh-keyscan -t ed25519 195.49.215.49 | sudo tee /etc/nika-isna/known_hosts >/dev/null
sudo chown "$SERVICE_USER:$SERVICE_GROUP" /etc/nika-isna/known_hosts
sudo chmod 600 /etc/nika-isna/known_hosts
```

Test the fixed command with that identity (read-only):

```bash
sudo -u "$SERVICE_USER" ssh -T -F /dev/null \
  -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/nika-isna/known_hosts \
  -o IdentitiesOnly=yes -o ClearAllForwardings=yes \
  -i /etc/nika-isna/probe_id_ed25519 \
  isna-probe@195.49.215.49 probe
```

The response should be the same one-record JSON as step 1.

Put these non-secret settings in **TEST only**
(`/var/www/nika-business-test/.env`); no change to production env:

```dotenv
ISNA_BIP_DIAG_SSH_HOST=195.49.215.49
ISNA_BIP_DIAG_SSH_USER=isna-probe
ISNA_BIP_DIAG_SSH_PORT=22
ISNA_BIP_DIAG_SSH_KEY=/etc/nika-isna/probe_id_ed25519
ISNA_BIP_DIAG_SSH_KNOWN_HOSTS=/etc/nika-isna/known_hosts
```

Then restart **only the TEST service** so it loads the updated environment:

```bash
sudo systemctl restart nika-business-test
sudo systemctl is-active nika-business-test
```

Open Android TEST → **Бухгалтерия → ИСНА TEST → Проверить доступность**.
A successful probe will say its source was `VPN VPS 47167 (через SSH)`
and report both TCP and HTTP status; it must also say SOAP was not sent.

## 3. What this does *not* enable

- No signing, SOAP forwarding, FNO submission or generic network proxy.
- A genuine WS-Security GOST SOAP request still needs an authorized transport
  signing implementation, matching transport certificate/private key, verified
  `senderId` and `serviceId`, and the **official ISNA payload XSD**.
- The Android signature of a harmless XML demo is **not** the transport
  signature and does not establish that the registered certificate matches.
- Do not enable a generic TCP/HTTP proxy to the gateway or put private
  signing keys in GitHub, TEST `.env`, logs or messages.
