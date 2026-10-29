# Smart Bridge IKEv2: controlled recovery after remote IKE_SA DELETE

## Verified evidence (2026-10-28/29)

On VPS `47167`, strongSwan 5.9.13 establishes the TEST IPsec connection
`nika-smartbridge-test` with source selector `195.49.215.49/32` and
destination `195.12.113.7/32`.

The journal contains **remote-initiated IKE_SA DELETEs**:
- 2026-10-28 17:35:36, after an establishment at 16:55:28.
- 2026-10-29 05:39:32, after an establishment at 04:18:47.

After receiving the DELETE, the connection disappeared; manual
`sudo ipsec up nika-smartbridge-test` successfully restored it. The
operator verified the fixed-target HTTP GET as the `www-data` user with
`tcpOk:true, httpOk:true, httpStatus:200`.

The strongSwan config already contains:
`auto=start`, `dpddelay=30s`, `dpdaction=restart`,
`keyingtries=%forever`. Do **not** change these blindly: DPD timeouts
do not necessarily trigger after a graceful remote IKE_SA DELETE.
The official reason for remote deletions remains unknown.

## Purpose and constraints

Install a narrowly scoped systemd **timer on the VPS**. Every five minutes
it checks `ipsec statusall`; it runs `ipsec up nika-smartbridge-test`
only if this exact connection has **no installed CHILD_SA**.

- Does not restart strongSwan, Nika, Gunicorn, Nginx or the VPS.
- Does not change existing PSK, IPsec settings or production branches.
- Does not send any SOAP messages, tax reports or EDS material.
- Uses `flock` to avoid concurrent execution.
- Attempts are capped by `timeout` and retried at most once per timer tick.
- An explicit remote DELETE could reflect a gateway maintenance/policy decision.
  Confirm with the Smart Bridge administrator if the peer repeatedly rejects
  reconnection; disable the timer in that case.

## Install on VPS 47167 (administrator action only)

After the TEST repository autodeploy has synchronized branch `test` to
`/var/www/nika-business-test`, review the checked-in script and units:

```bash
cd /var/www/nika-business-test
sudo git rev-parse --short HEAD
bash -n scripts/isna_vpn_watchdog.sh
sudo install -o root -g root -m 0750 scripts/isna_vpn_watchdog.sh /usr/local/sbin/nika-isna-vpn-watchdog
sudo install -o root -g root -m 0644 ops/systemd/nika-isna-vpn-watchdog.service /etc/systemd/system/nika-isna-vpn-watchdog.service
sudo install -o root -g root -m 0644 ops/systemd/nika-isna-vpn-watchdog.timer /etc/systemd/system/nika-isna-vpn-watchdog.timer
sudo systemctl daemon-reload
sudo systemctl enable --now nika-isna-vpn-watchdog.timer
```

The timer only becomes active after those commands have been run on the VPS;
merging files into the TEST branch **does not install or enable it**.

## Verify without disrupting the live tunnel

```bash
sudo systemctl list-timers nika-isna-vpn-watchdog.timer --no-pager
sudo systemctl start nika-isna-vpn-watchdog.service
sudo systemctl status nika-isna-vpn-watchdog.service --no-pager -l
sudo journalctl -u nika-isna-vpn-watchdog.service -n 30 --no-pager
sudo ipsec statusall | grep -A 8 'Security Associations'
sudo -u www-data python3 /var/www/nika-business-test/scripts/isna_gateway_probe.py
```

The one-shot service should exit `0` and be inactive/dead after completion
(this is normal, not a service failure). The **timer** should show active.

**Do not force the VPN down on the production-hosting VPS to test the watchdog.**
Wait for any natural remote DELETE and inspect systemd logs for a restoration.

## Disable/rollback

```bash
sudo systemctl disable --now nika-isna-vpn-watchdog.timer
```

To uninstall, after disabling:

```bash
sudo rm -f /etc/systemd/system/nika-isna-vpn-watchdog.service /etc/systemd/system/nika-isna-vpn-watchdog.timer /usr/local/sbin/nika-isna-vpn-watchdog
sudo systemctl daemon-reload
```

If the gateway keeps sending DELETE quickly after each reconnect, ask its
administrator about inactivity/session policies; the timer is an availability
mitigation, not a permanent explanation of the underlying reason.
