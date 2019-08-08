# Intent
Facilitate monitoring of Jenkins servers in your enterprise organisation.

# Pre-requisites
1. System running CentOS v7.x (this is your monitoring agent)
2. Additional system Packages
   - netcat (preferred 7.50)
3. Python v2.7.x
4. Additional Python packages
   - paramiko (preferred 2.6.0)

# Assumptions
1. In the server running the Jenkins service, SSH service should be enabled, to accept incoming connection requests at port #22.
2. For the user's login id, that shall execute this script, enable passwordless authentication (from the monitoring agent) to connect to the server running the Jenkins service.
3. Jenkins is installed as system package (using, for example, `yum install ...`)

# Monitor what?
Iterate through the entries in `servers.yaml`, and for each Jenkins host
that's in production (`active: true`), perform series of health checks.

a. Initial Health Checks
- ICMP response
- Scan ports,
      - SSH (22)
      - HTTPS (8443) [ *as set in `servers.yaml`* ]

b. Extended Health Checks
- Capability of the Server, running the Jenkins service, to accept incoming SSH connection requests.
- Status of Jenkins process in the Jenkins server.
- Measure (thrice) the HTTP response with decreasing `timeout`.

# How to execute?
1. Clone this repository
2. To monitor the Jenkins instance, update these entries in `servers.yaml`. All of these entries together constitute the server info block that's used by the tool.
   - active: `true`
   - host: `jenkins-hostname`
   - url:  `"URL-to-jenkins"`
   - port: `jenkins-port`
2. Execute the script, like this,
```
cd <repo-cloned-dir>
python bin/monitor.py
```

# Monitor output
For every execution of the script, the output is,
1. Directed to terminal console.
2. Also saved in, *jenkins_monitor_<date_time>.log*

# FAQ
1. Retain the server in `servers.yaml` but do _not_ consider for monitoring. Is it possible?

- **YES**, in `servers.yaml`, set the server as inactive, in the the info block for the desired server, like this.
  - `active: false`

2. What's the plan to support platforms other than CentOS?
Please see [this issue](https://github.com/mramanathan/jenmonitor/issues/1)