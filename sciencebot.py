#!/usr/bin/env python

#twisted imports
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, ssl, defer
from twisted.python import log
from sys import stdout

#system imports
import time, sys

# ganeti imports
import urllib2
import json

# fun imports
import re
import datetime

#sciencebot imports

import scienceconfig

# gentleman imports
import sys

sys.path.append('gentleman/')

import gentleman.async
import gentleman.base

def getInstanceNumber():
    f = urllib2.urlopen("https://" + scienceconfig.ganetihost + ':5080/2/instances')
    response = f.read()
    obs = json.loads(response)
    return len(obs)


class Counter(object):
    def __init__(self):
        self._value = 0

    def increment(self):
        self._value += 1

    def get(self):
        return self._value

class MessageLogger:
    """
    An independent logger class (because separation of application
    and protocol logic is a good thing).
    """
    def __init__(self, file):
        self.file = file

    def log(self, message):
        """Write a message to the file."""
        timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
        self.file.write('%s %s\n' % (timestamp, message))
        self.file.flush()

    def close(self):
        self.file.close()

class Echo(protocol.Protocol):
    def dataReceived(self, data):
        stdout.write(data)

class RelayClient(protocol.Protocol):
    def dataReceived(self, data):
        stdout.write(data)

class LogBot(irc.IRCClient):
    """A logging IRC bot."""

    nickname = scienceconfig.nickname
    versionName = "versionName"
    versionNum = "versionNum"
    versionEnv = "versionEnv"
    sourceURL = "http://github.com/nibalizer/sciencebot"
    lineRate = scienceconfig.lineRate
    channels = []
    channelkey = scienceconfig.channelkey

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.logger = MessageLogger(open(self.factory.filename, "a"))
        self.logger.log("[connected at %s]" %
                        time.asctime(time.localtime(time.time())))
        self.factory.ircservers.append(self)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        self.logger.log("[disconnected at %s]" %
                        time.asctime(time.localtime(time.time())))
        self.logger.close()
        self.factory.ircservers.remove(self)

    # callbacks for events

    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        self.msg("NickServ", "identify %s" % scienceconfig.userpassword )
        self.join(self.factory.channel, self.channelkey)

    def joined(self, channel):
        """This will get called when the bot joins the channel."""
        self.logger.log("[I have joined %s]" % channel)
        self.channels.append(channel)

    def privmsg(self, user, channel, msg):
        """This will get called when the bot receives a message."""
        user = user.split('!', 1)[0]
        self.logger.log("<%s> %s" % (user,msg))


        # Check to see if they're sending me a private message
        if channel == self.nickname:
            reply = "I'm not sure what we have to say to each other directly."
            self.msg(user, reply)
            # Check to see if bot has been told to join multiple channels 

            if msg.startswith("join"):
                channel = " ".join(msg.split()[1:])
                self.join(channel)
                self.logger.log("[I have joined %s]" % channel)
                msg = "Oh, you wanted that. I see."
                self.msg(user, msg)
                return

        # Otherwise check to see if it is a message directed at me
        if msg.startswith(self.nickname + ":"):
            msg = "%s: I am a derpy bot, help will be written later" % user
            self.msg(channel, msg)
            self.logger.log("<%s> %s" % (self.nickname, msg))
            self.describe(channel, "science")
            self.logger.log("<%s> %s" % (self.nickname, "science"))

        # Check to see if it is asking for count

        if msg.startswith("count"):
            msg =  str(self.factory.counter.get())
            self.msg(channel, msg)
            self.logger.log("<%s> %s" % (self.nickname, msg))

        # check to see if it is incrementing the count

        if msg.startswith("more"):
            self.factory.counter.increment()

        # Check to see if user is trying to irc over irc

        if msg.startswith("SERVERPRIVMSG"):
            msg = " ".join(msg.split()[1:])
            for ircserver in self.factory.ircservers:
                if ircserver is self:
                    continue
                ircserver.msg(channel, msg)

        # irc over irc is good
        # broadcast to all channels except the one the command 
        # came from

        if msg.startswith("BROADCAST"):
            msg = " ".join(msg.split()[1:])
            print self.channels
            for chan in self.channels:
                if chan == channel:
                    continue
                self.msg(chan, msg)

        # Use privmsg kind close to rfc spec
        if msg.startswith("PRIVMSG"):
            results = re.split('PRIVMSG (#?\w*) :(.*)', msg)
            if len(results) < 4:
                self.msg(channel, "Error in PRIVMSG")
            else:
                empty, dest_chan, message, empty2 = results
                self.msg(dest_chan, message)


        # check to see if we're doing ganeti things

        if msg.startswith("ganeti "):
            #drop into ganeti command mode

            # pop off the next argument
            remaining_args = " ".join(msg.split()[1:])

            if remaining_args == "version":
                #pop off the next argument
                remaining_args = " ".join(remaining_args.split()[1:])

                # base case
                if remaining_args == "":
                    r = gentleman.async.TwistedRapiClient(scienceconfig.ganetihost)
                    getVer = gentleman.base.GetVersion(r)
                    def printGanetiAPIVer(d):
                        d = str(d)
                        reply = "{0} using Ganeti API Version {1}".format(scienceconfig.ganetihost, d)
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))
                    getVer.addCallback(printGanetiAPIVer)

            if remaining_args == "info":
                #pop off the next argument
                remaining_args = " ".join(remaining_args.split()[1:])

                # base case
                if remaining_args == "":
                    r = gentleman.async.TwistedRapiClient(scienceconfig.ganetihost)
                    info = gentleman.base.GetInfo(r)
                    def printInfo(d):
                        reply = "Cluster info:"
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))
                        for k, v in d.iteritems():
                            reply = "{0} => {1}".format(k, v)
                            self.msg(channel, reply)
                            self.logger.log("<%s> %s" % (self.nickname, reply))
                    info.addCallback(printInfo)


            if remaining_args.startswith("instance "):
                #pop off the next argument
                remaining_args = " ".join(remaining_args.split()[1:])
                print "made it here"
                print remaining_args

                # 'all' argument
                if remaining_args == "all":
                    """
                    List all instances.
                    """
                    r = gentleman.async.TwistedRapiClient(scienceconfig.ganetihost)
                    instances = gentleman.base.GetInstances(r)
                    def printInstances(d):
                        reply = "Instances: {0}".format(len(d))
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))
                        insts = [i["id"] for i in d]
                        reply = ", ".join(insts)
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))
                    instances.addCallback(printInstances)

                # 'info' argument
                if remaining_args.startswith("info"):
                    """
                    Print out info on a specific instance.
                    """
                    remaining_args = " ".join(remaining_args.split()[1:])
                    query_instance = remaining_args
                    r = gentleman.async.TwistedRapiClient(scienceconfig.ganetihost)
                    instance = gentleman.base.GetInstance(r, query_instance)
                    def printInstanceInfo(d):
                        """
                        Format the node information in a human reable way.
                        """

                        reply = "Instances {0}".format(d['name'])
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))

                        reply = "On: {0}, Disks: {1}, Ram: {2}, CPUs: {3} ".format(d['oper_state'], d['disk_template'], d['oper_ram'], d['oper_vcpus'])
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))

                        ctime = d['ctime']
                        mtime = d['mtime']
                        cTime = (datetime.datetime.fromtimestamp(float(ctime)).strftime('%Y-%m-%d %H:%M:%S'))
                        mTime = (datetime.datetime.fromtimestamp(float(mtime)).strftime('%Y-%m-%d %H:%M:%S'))

                        reply = "Mac: {0}, Status: {1}, Created: {2}, Modified: {3} ".format(d['nic.macs'][0], d['status'], cTime, mTime)
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))

                        if len(d['snodes']) == 0:
                            snodes = "No secondary node"
                        else:
                            snodes = ";".join(map(str,d['snodes']))

                        reply = "Primary: {0}, Secondary: {1}, Disk Size: {2}, Bridge: {3} ".format(d['pnode'], snodes, ";".join(map(str,d['disk.sizes'])), d['nic.bridges'][0])
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))

                        reply = "To connect ssh -L 5900:localhost:{1} {0}".format(d['pnode'], d['network_port'])
                        self.msg(channel, reply)
                        self.logger.log("<%s> %s" % (self.nickname, reply))

                    instance.addCallback(printInstanceInfo)



    def action(self, user, channel, msg):
        """This will get called when the bot sees someone do an action."""
        user = user.split('!', 1)[0]
        self.logger.log("* %s %s" % (user, msg))

    # irc callbacks

    def irc_NICK(self, prefix, params):
        """Called when an IRC user changes their nickname."""
        old_nick = prefix.split('!')[0]
        new_nick = params[0]
        self.logger.log("%s is now known as %s" % (old_nick, new_nick))

    # for fun, oveEchorride the method that determines how a nickname is changed on
    # collisions. The default method appends an underscore.

    def alterCollidedNick(self, nickname):
        """
        Generate an altered version of a nickname that caused a collision in an
        effort to create an unused related name for subsequent registration.
        """
        return nickname + '^'


class EchoClientFactory(protocol.ClientFactory):
    def startedConnecting(self, connector):
        print 'Started to connect.'

    def buildProtocol(self, addr):
        print 'Connected.'
        return Echo()

    def clientConnectionLost(self, connector, reason):
        print 'Lost Connection. Reason:', reason

    def clientConnectionFailed(self, connector, reason):
        print 'Connection failed. Reason:', reason


class RelayClientFactory(protocol.ClientFactory):
    def startedConnecting(self, connector):
        print 'Started to connect.'

    def buildProtocol(self, addr):
        print 'Connected.'
        return RelayClient()

    def clientConnectionLost(self, connector, reason):
        print 'Lost Connection. Reason:', reason

    def clientConnectionFailed(self, connector, reason):
        print 'Connection failed. Reason:', reason


class LogBotFactory(protocol.ClientFactory):
    """A factory LogBots.
    A new protocol instance will be created each time we connect to the server.
    """

    def __init__(self, channel, filename, counter):
        self.channel = channel
        channelkey = scienceconfig.channelkey
        self.filename = filename
        self.counter = counter
        self.ircservers = []

    def buildProtocol(self, addr):
        p = LogBot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, recconect to server."""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Connection failed:", reason
        reactor.stop()

if __name__ == '__main__':
    #initialize logging
    log.startLogging(sys.stdout)

    counter = Counter()
    # create factory protocol and application
    f = LogBotFactory(scienceconfig.channel, scienceconfig.logfile, counter)
    #e = EchoClientFactory()
    #r = RelayClientFactory()

    #connect factory to this host and port
    #reactor.connectTCP("irc.freenode.net", 6667, f)
    #reactor.connectTCP("irc.cat.pdx.edu", 6667, f)
    reactor.connectSSL("irc.cat.pdx.edu", 6697, f, ssl.ClientContextFactory())
    #reactor.connectTCP("localhost", 8888, e)
    #reactor.connectTCP("localhost", 8889, r)

    # run bot
    reactor.run()
