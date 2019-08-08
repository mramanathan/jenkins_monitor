#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-

import logging, logging.handlers
import yaml
import sys
import os
import datetime as dt
from configobj import ConfigObj
import base64

import smtplib
from email import Encoders
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.MIMEMultipart import MIMEMultipart
from email.Utils import formatdate

from monitor_lib import JenkinsMonitor

from twilio.rest import Client

mail_config = "mail_config.txt"
jenkins_health_status = {}

timenow = dt.datetime.today()
timenow = timenow.ctime().replace(" ", "_")
logfile = 'jenkins_monitor_' + timenow + '.log'

def resetLogfile(logfile):
    if os.path.exists(logfile):
        with open(logfile, "w") as mlog:
            mlog.write("")

    return logfile


logger = logging.getLogger("jenkins")
logger.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
formatter = logging.Formatter('%(asctime)s :%(name)s - %(levelname)s -- Line:%(lineno)d --- %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S')
#console_handler
ch = logging.StreamHandler()
ch.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
ch.setFormatter(formatter)
logger.addHandler(ch)
#file handler
resetLogfile(logfile)
fh = logging.FileHandler(logfile)
fh.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
fh.setFormatter(formatter)
logger.addHandler(fh)

def initHealthCheck(host,url,jenkins_port):
    """
        1. ICMP response
        2. Scan ports (22, 8443)
    """
    init_health = ""

    jenkins = JenkinsMonitor(host,url,jenkins_port)
    logger.info("[[ START -- Initial Health Checks ]]: Running initial health checks in {0}".format(host))
    if jenkins.checkICMP() == "True" and jenkins.checkPorts() == "True":
        init_health = "FINE"
        logger.info("Initial health checks on the server host, {0}, is {1}.".format(host,init_health))
    else:
        init_health = "FIRE"
        logger.error("Initial health checks indicate the server host, {0}, is on {1}.".format(host,init_health))

    return init_health 

def xtendedHealthCheck(host,url,jenkins_port):
    """
        1. Is Jenkins service running in the given Jenkins host?
        2. Gauge the basic HTTP response from the given jenkins-url
    """
    xtended_health = ""

    jenkins = JenkinsMonitor(host,url,jenkins_port)
    logger.info("[[ START -- Extended Health Checks ]]: Running extended health checks in {0}".format(host))

    if jenkins.checkService() == "True" and jenkins.checkHTTPResponse() == "True" :
        xtended_health = "OK"
        logger.info("Extended health checks on the server host, {0}, is {1}.".format(host,xtended_health))
    else:
        xtended_health = "NOTOK"
        logger.error("Extended health checks on the server host, {0}, is {1}.".format(host,xtended_health))
    
    return xtended_health

def checkJenkins(host,url,jenkins_port):
    """
        Jenkins is healthy if the results, from the combined tests of 
        initHealthCheck and xtendedHealthCheck, are positive.
    """
    jenkins_health = ""

    if initHealthCheck(host,url,jenkins_port) == "FINE" and xtendedHealthCheck(host,url,jenkins_port) == "OK":
        logger.info("[[  DONE -- checkJenkins ]]: All checks in {0} have PASSED.".format(host))
        jenkins_health = "ALL_OKAY"
    else:
        logger.info("[[  DONE -- checkJenkins ]]: Some checks in {0} have FAILED.".format(host))
        jenkins_health = "INVESTIGATION_NEEDED"

    # Used for reporting
    jenkins_health_status[host] = jenkins_health

    return None

def send_report():
    """
        1. Notify the team via mail, for normal reporting and when issues are observed.
        2. Send text message to <jenkins-admin's-cell>, if issues are found
    """
    
    overall_health = ""

    header = 'Content-Disposition', 'attachment; filename="%s"' % logfile
    
    report_date = formatdate(localtime=True)

    generic_text = 'Log of the various checks performed by the monitoring script is attached.'

    newline_marker = '\n\n'

    if "INVESTIGATION_NEEDED" in jenkins_health_status.values():
        overall_health += "INVESTIGATION_NEEDED"
    else:
        overall_health += "ALL_OKAY"

    cfg = ConfigObj(mail_config)
    cfg_dict = cfg.dict()

    from_addr = cfg_dict['smtp']['from_address']
    to_addr = cfg_dict['smtp']['notify_team']

    msg = MIMEMultipart()
    msg['To'] = to_addr
    msg['From'] = from_addr
    msg['Subject'] = "Jenkins Health Monitor Report :: "  + overall_health + ", as of, " + report_date
    msg['Date'] = report_date

    # the message content
    mail_body = ""
    mail_body += "Jenkins Health Report : Short Summary"
    mail_body += newline_marker
    for k,v in jenkins_health_status.items():
        mail_body += "===> \tHealth checks on '{0}' indicate the status is :: {1}".format(k,v)
        mail_body += "\n\n"

    mail_body += generic_text
    msg.attach( MIMEText(mail_body) )

    attachment = MIMEBase('application', "octet-stream")
    try:
        with open(logfile, "rb") as fh:
            data = fh.read()
        attachment.set_payload( data )
        Encoders.encode_base64(attachment)
        attachment.add_header(*header)
        msg.attach(attachment)
    except IOError:
        msg = "Error opening attachment file %s" % logfile
        logger.error(msg)
        sys.exit(1)

    mail_host = cfg_dict['smtp']['mail_server']
    mail_port = cfg_dict['smtp']['mail_port']

    server = smtplib.SMTP(mail_host, mail_port)
    # server.set_debuglevel(True) # show communication with the server
    try:
        server.sendmail(from_addr, [to_addr], msg.as_string())
    finally:
        server.quit()

    return None

def sms_alert():
    """
        For those Jenkins' instances with issues, alert via SMS.
    """

    text_content = ""
    text_message = ""
    # phone numbers should be prefixed and suffixed with single quotes
    source_phone = '+'
    to_phone     = '+'

    with open("twilio.config", "r") as cfg:
        twcfg = cfg.readlines()

    account_sid = base64.b64decode(twcfg[0].split("= ")[-1])
    auth_token = base64.b64decode(twcfg[1].split("= ")[-1])
    client = Client(account_sid, auth_token)

    for k,v in jenkins_health_status.items():
        if v == "INVESTIGATION_NEEDED":
            text_content += ", ".join("{0}:{1}".format(k,v))

    source_phone += base64.b64decode(twcfg[2].split("= ")[-1]) + "'"
    to_phone     += base64.b64decode(twcfg[3].split("= ")[-1]) + "'"
    text_message = client.messages \
                    .create(
                        body=text_content,
                        from_=source_phone,
                        to=to_phone
                    )

    logger.info("Twilio text message, {}".format(text_message.sid))
    
    return None

def cleanup_log():
    #Avoid cluttering 'build' user's home-dir
    if os.path.exists(logfile):
        os.remove(logfile)

    return None

def main():
    """
        Iterate thru' each entry in 'servers.yaml'.
        On those instances that are 'true'ly active, run the health checks
        and report the results on STDOUT, also collected in 'jenkins_monitor.log'.
    """

    with open("servers.yaml", "r") as servers:
        jenkins=yaml.load(servers, Loader=yaml.BaseLoader)

    for i in range(len(jenkins['servers'])):
        tempdict = jenkins['servers'][i]
        """
            If the instance is in production (active param set to 'true'),
            then run the checks on this Jenkins engine.
        """
        if tempdict['active'] == "true":
            logger.info("Jenkins instance, {0}, is active in production".format(tempdict['host']))
            checkJenkins(tempdict['host'],tempdict['url'],tempdict['port'])
        else:
            logger.info("Jenkins instance, {0}, is _not active_ in production".format(tempdict['host']))

    send_report()
    cleanup_log()

    # Like me, if you're running on Twilio free account
    """
    if "INVESTIGATION_NEEDED" in jenkins_health_status.values():
        sms_alert()
    """

if __name__ == '__main__':
    main()