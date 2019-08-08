#!/usr/bin/env python

# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import subprocess
import json
import logging
import requests
import paramiko
from paramiko import BadHostKeyException, AuthenticationException, SSHException
import socket
import time
import timeit
import datetime

logger = logging.getLogger("jenkins.monitor_lib")

class JenkinsMonitor(object):
    
    # Base class that's responsible to check and report the health of Jenkins
    
    def __init__(self, jenkins_host,jenkins_url,jenkins_port):
        
        """ 
            Works with Python v2.7.x, not tried in v3.x
        """
       
        self.jenkins_host     = jenkins_host
        self.jenkins_url      = jenkins_url
        self.jenkins_port     = jenkins_port
        self.jenkins_domain   = ".".join(self.jenkins_url.split(".")[1:])
        self.job              = 'job'
        self.jsonapi          = '/api/json?pretty=true'
        self.user             = os.environ["USER"]
        self.ssh_timeout      = 45.0

        # orgjenkins.orgdomain.com
        self.jenkins_server = self.jenkins_host+self.jenkins_domain

    def checkICMP(self):
        """
            Tested from a system running centOS v7.6
        """
        icmp_result = ""
        resp        = ""

        logger.info("[[ checkICMP ]]: Running ICMP checks in {0}".format(self.jenkins_host))
        try:
            logger.info("[checkICMP]: Is the host, {}, running Jenkins, live on the network?".format(self.jenkins_host))
            resp = os.system("ping -c 7 " + self.jenkins_host)
            """
                PING jenkins-server.mydomain.com (192.168.1.1) 56(84) bytes of data.
                64 bytes from jenkins-server.mydomain.com (192.168.1.1)  icmp_seq=1 ttl=62 time=248 ms
                
                --- jenkins-server.mydomain.com ping statistics ---
                1 packets transmitted, 1 received, 0% packet loss, time 0ms
                rtt min/avg/max/mdev = 248.855/248.855/248.855/0.000 ms
                >>> resp
                0

                [[ OR ]]

                ping: unknown host super-jekins.mydomain.com
                >>> resp
                512
            """

            if resp == 0:
                logger.info("== ICMP response received.")
                icmp_result = "True"
            else:
                logger.error("== ICMP response not received.")
                icmp_result = "False"
        except Exception as error:
            icmp_result = "False"
            logger.error("ICMP check failed with error, {0}".format(error))

        return icmp_result

    def checkPorts(self):
        """
            Limit to two ports: SSH, and jenkins port
            Assumptions
            1. SSH service is running on #22
            2. nc utility is installed on the centOS system
        """

        scan_result  = ""
        resp         = ""

        ports_to_scan = [22, self.jenkins_port]
        logger.info("[[ checkPorts ]]: Running port checks in {0}".format(self.jenkins_host))
        logger.info("[checkPorts]: Scanning for open ports in the host, {0}".format(self.jenkins_host))
        for this_port in ports_to_scan:
            this_port = str(this_port)
            logger.info("[checkPorts]: Checking for port #{0}".format(this_port))
            sshport = 'nc -z ' + self.jenkins_host + " " + this_port
            resp = subprocess.call([sshport], shell=True)
            if resp == 0:
                logger.info("== Scanning port #{0} succeeded.".format(this_port))
                scan_result = "True" 
            else:
                logger.error("== Scanning port #{0} failed.".format(this_port))
                scan_result = "False"

        return scan_result

    def sshHandle(self):
        """
            Dependency:
            Have 'paramiko' installed in the centos system
        """

        initial_wait=0

        ssh_client = paramiko.SSHClient()
        """
            Retain this line to avoid errors, like,
            Server 'myserver-jenkins.domain.com' not found in known_hosts
        """
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        time.sleep(initial_wait)
        logger.info("SSH handle instantiated...")

        return ssh_client

    def checkSSH(self):
        """
            Pre-requisites: 
	    1. Setup passwordless authentication using SSH keys, for that generic user 
	       that's setup to run the build jobs in the CI environment.
            2. As that 'build' user, at least once, SSH into the Jenkins server host.
	       This step helps to validate that, indeed, passwordless SSH works between
	       the Jenkins server and the agent, that shall serve to monitor the former.
        """

        ssh_status = "False"

        interval=0
        retries=3

        ssh_client = self.sshHandle()

        logger.info("[[ checkSSH ]]: Checking the SSH service in {0}".format(self.jenkins_host))

        for x in range(retries):
            try:
                #Preferred user is 'build'
                ssh_client.connect(self.jenkins_server, username=os.environ['USER'], timeout=self.ssh_timeout, auth_timeout=self.ssh_timeout)
                print("[[Run {0}]] ~> SSH connection check status in {1} :: {2}".format(x, self.jenkins_server, "PASSED"))
                if ( x == retries-1):
                        ssh_status = "True"
                        print("\n\n[SSH Checks]:~> SUCCESSFUL!\n")
                        logger.info("\n[SSH Checks]:~> SUCCESSFUL!\n")
                        return ssh_status
            except (BadHostKeyException, AuthenticationException, SSHException, socket.error, socket.gaierror) as err:
                print(err)
                time.sleep(interval)
            finally:
                ssh_client.close()

        return ssh_status

    def checkService(self):
        """
            Is the Jenkins service active in the process tree?
        """

        service_alive     = "False"

        """
            Assumption ::
            jenkins is started using java that picks the jenkins pkg, like, (with various other inputs).
            -jar /usr/lib/jenkins/jenkins.war

            All these inputs are gathered from /etc/sysconfig/jenkins?
        """
        jenkins_service = 'ps -eaf ' + ' | grep -i "jenkins.war" ' + ' | grep -v grep ' + ' | cut -d" " -f3 '

        if self.checkSSH() == "True":
            logger.info("[[ checkService ]]: Checking the Jenkins service in {0}".format(self.jenkins_host))
            ssh_client = self.sshHandle()

            try:
                logger.info("Trying to scan the process table in {0} to check active Jenkins service".format(self.jenkins_host))
                ssh_client.connect(self.jenkins_server, username=os.environ['USER'], timeout=self.ssh_timeout, auth_timeout=self.ssh_timeout)
                stdin, stdout, stderr = ssh_client.exec_command(jenkins_service)
                service_out = stdout.read()
                pid = service_out.strip("\n")
                logger.info("{0} is the process id of the active Jenkins service in {1}".format(pid, self.jenkins_host))
                service_alive = "True"
            except (BadHostKeyException, AuthenticationException, SSHException, socket.error, socket.gaierror) as err:
                logger.error("Jenkins service could not be completed, {0}".format(err))
                logger.error("Errors reported while checking for Jenkins service in {0}".format(self.jenkins_host))
                service_err = stderr.read()
                logger.error("{0}".format(service_err))
            finally:
                ssh_client.close()

        return service_alive

    def setTimer(self):
        set_time = timeit.default_timer()

        return set_time

    def checkHTTPResponse(self):
        """
            Check for HTTP response.
            1. 200 is OK
            2. non-200 is a problem

            1. Start with a timeout of 30seconds for the first attempt.
            2. Decrease this timeout value by test_count * timeout_interval 
            i.e timeout = timeout_base - (test_count*timeout_interval)
            In the 2nd iteration, new timeout will be, 25
            In the 3rd iteration, new timeout will be, 15
        """
        http_response    = ""

        timeout_base     = 30
        test_count       = 3
        timeout_interval = 5

        # https:/mycompany-jenkins.company.domain.com:8443
        jenkins_https = self.jenkins_url + ":" + self.jenkins_port

        logger.info("[[ checkService ]]: Checking for HTTP response from the Jenkins service running in {0}".format(self.jenkins_host))
        for i in range(test_count):
            resp = ""
            if i == 0:
                http_timeout = timeout_base
            else:
                http_timeout = http_timeout-(i*timeout_interval)

            logger.info("Timeout for requests set to, {0}".format(http_timeout))
            resp_start = self.setTimer()
            resp = requests.get(jenkins_https, timeout=http_timeout)
            resp_end = self.setTimer()
            resp_code = resp.status_code
            resp_time = str(datetime.timedelta(seconds=resp_end-resp_start)) 

            if resp_code == 200:
                http_response = "True"
                logger.info("Attmpt {0}, HTTP response, {1}".format(i,resp_code))
                logger.info("Attempt {0}, HTTP response time, {1}".format(i,resp_time))
            else:
                http_response = "False"
                logger.error("Attmpt {0}, HTTP response, {1}".format(i,resp_code))
                logger.info("Attempt {0}, HTTP response time, {1}".format(i,resp_time))

        return http_response