# Subxid Support

Subuid and subgid (subxid) support is required to achieve the full functionality with a non-root Podman.
This document describes how subxid support is handled at NERSC with some code examples.  This is provided
as a reference example.  Sites will require tailored apporaches based on their user management system,
directory services, and batch environment


## Subxid range management

NERSC uses an in-house management system called Iris (https://ieeexplore.ieee.org/abstract/document/9355247).
Since Iris is already responsible for managing UIDs and GIDs, adding subxid support was a natural choice.
Iris ensures users do not recieve overlapping ranges.  The ranges are stored with in Iris's internal database
and stored in NERSC's LDAP tables.  Currently these are stored in a description field in the format of `<uid>:<start xid>:<length>`.
NERSC may adjust this in the future to work with emerging standard.  Services can query LDAP to extract the subxid 
values for each user.

## Subxid service

An subxid service is used to cache and serve up the subxid values at scale.  This avoids placing heavy pressure on the LDAP service.
The subxid service is very basic.  A python script queries LDAP for all users and generates an output format compliant with `/etc/subuid` and `/etc/subgid`.  This is written to a temporary file and served via an nginx server.  The service is deployed via Helm with two pods that share a volume.  One pod periodically runs the generation script and the other runs nginx.

## Subxid login and compute node integration

The local `/etc/subuid` and `/etc/subgid` files are updated on login and compute nodes by a systemd service and timer.  The service fetches the map from the subxid service and writes them to the local files.

Here is the service definition.

```
[Unit]
Description=Do subxid update

[Service]
Type=oneshot
Nice=5
IOSchedulingClass=idle
ExecStart=/bin/bash -c 'wget -O /etc/subuid --tries=1 --quiet http://{{ subxid_ip }}/subxid && cp /etc/subuid /etc/subgid'

[Install]
WantedBy=nersc.target
```

The timer definition triggers the service every hour.

```
[Unit]
Description=Do hourly subxid update
Documentation=man:mandb(8) man:catman(8)

[Timer]
OnCalendar=hourly
AccuracySec=1us
Persistent=true
OnBootSec=15min
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
```

## Alternate Approaches

As noted above, the NERSC implementation for subxid support is bespoke.  A more standardized
implementation can be found in FreeIPA.  This implemenation allows FreeIPA to manage the ranges
and they are stored in a special object class (`ipaTrustedADDomainRange`).  Enhancements to System Security Services Daemon (sssd)
allow it to cache the subuid/subgid from FreeIPA and is managed via `/etc/nsswitch.conf`.  Support for
providers other than FreeIPA has been added to sssd (e.g. LDAP).  See References for more details.

## References:
- https://freeipa.readthedocs.io/en/ipa-4-11/designs/subordinate-ids.html for details.
- https://access.redhat.com/solutions/6961540 (requires a login)
