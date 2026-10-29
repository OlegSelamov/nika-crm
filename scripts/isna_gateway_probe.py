#!/usr/bin/env python3
"""Fixed-target, read-only gateway probe for the IPsec VPN host (47167).

Designed for an SSH authorized_keys *forced command*, as a dedicated
non-privileged account. No arguments, no access to arbitrary URLs, no SOAP
requests, no forwarding. Prints a single non-sensitive JSON object.
"""
import http.client
import json
import socket

SOURCE_IP = "195.49.215.49"
GATEWAY_IP = "195.12.113.7"
GATEWAY_PORT = 80
WSDL_PATH = "/bip-sync-wss-gost/"


def main():
    result = {"schema": 1, "tcpOk": False, "httpOk": False, "httpStatus": None}
    try:
        with socket.create_connection(
            (GATEWAY_IP, GATEWAY_PORT), timeout=5, source_address=(SOURCE_IP, 0)
        ):
            result["tcpOk"] = True
    except OSError:
        pass

    if result["tcpOk"]:
        connection = None
        try:
            connection = http.client.HTTPConnection(
                GATEWAY_IP, GATEWAY_PORT,
                timeout=5, source_address=(SOURCE_IP, 0),
            )
            # Only a fixed HTTP GET. Never a SOAP POST or arbitrary path.
            connection.request("GET", WSDL_PATH, headers={"Accept": "text/xml"})
            response = connection.getresponse()
            result["httpStatus"] = response.status
            result["httpOk"] = response.status == 200
        except (OSError, http.client.HTTPException):
            pass
        finally:
            if connection is not None:
                connection.close()
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
