#!/usr/bin/env python3
# coding=utf-8
# This file is part of the uberserver (GPL v2 or later), see LICENSE

import socket, inspect
import time
import threading
import traceback
import random
#import ssl
import sys
import argparse
#import tlsclient

from hashlib import md5

from base64 import b64decode as SAFE_DECODE_FUNC

import base64

#TODO:
# tls for hosting battles
# argparse stuff
# multiproc
# handle disconnect

# States:
# INIT <-> LOGGEDIN <-> JOININGBATTLE -> JOINEDBATTLE

import enum

class State(enum.Enum):
	INIT = 0
	LOGGEDIN = 1
	JOININGBATTLE = 2
	INBATTLE = 3
	HOSTING = 4

USE_THREADS = False

NUM_CLIENTS = 50 if USE_THREADS == True else 50
NUM_UPDATES = 100000
CLIENT_NAME = "[teh]stress[%04d]"
CLIENT_EMAIL = "[teh]stress[%04d]_mysterme@gmail.com"
MAGIC_WORDS = "SqueamishOssifrage"

HOST_SERVER = ("server5.beyondallreason.info", 8200)
MAIN_SERVER = ("lobby.springrts.com", 8200)
TEST_SERVER = ("lobby.springrts.com", 7000)
BACKUP_SERVERS = [
	("lobby1.springlobby.info", 8200),
	("lobby2.springlobby.info", 8200),
]

class BattleStatus:
	def __init__(self, battle_status):
		battle_status = int(battle_status)
		if not (0 <= battle_status <= 2147483647):
			raise ValueError("Battle status out of range")

		self.battle_status = battle_status

		# Define the bit positions
		self.ready = battle_status & 0b1
		self.team = (battle_status >> 1) & 0b1111
		self.ally_team = (battle_status >> 6) & 0b1111
		self.mode = (battle_status >> 10) & 0b1
		self.sync_status = (battle_status >> 22) & 0b11
		self.side = (battle_status >> 24) & 0b1111

	def __str__(self):
		return f"Ready: {self.ready}, Team: {self.team}, Ally Team: {self.ally_team}, " \
			f"Mode: {self.mode}, Sync Status: {self.sync_status}, Side: {self.side}"

	def encode(self):
		encoded = 0
		encoded |= self.ready & 0b1
		encoded |= (self.team & 0b1111) << 1
		encoded |= (self.ally_team & 0b1111) << 6
		encoded |= (self.mode & 0b1) << 10
		encoded |= (self.sync_status & 0b11) << 22
		encoded |= (self.side & 0b1111) << 24
		return encoded
		
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		else:
			return False
		
	def __ne__(self, other):
		return not self.__eq__(other)
	
class Status:
	def __init__(self, status):
		status = int(status)  # Convert the input text to an integer

		if not (0 <= status <= 2147483647):
			raise ValueError("Status out of range")

		self.status = status

		# Define the bit positions
		self.in_game = status & 0b1
		self.away_status = (status >> 1) & 0b1
		self.rank = (status >> 2) & 0b111
		self.access_status = (status >> 5) & 0b1
		self.bot_mode = (status >> 6) & 0b1

	def __str__(self):
		return f"In Game: {self.in_game}, Away Status: {self.away_status}, " \
			f"Rank: {self.rank}, Access Status: {self.access_status}, Bot Mode: {self.bot_mode}"

	def encode(self):
		encoded = 0
		encoded |= self.in_game & 0b1
		encoded |= (self.away_status & 0b1) << 1
		encoded |= (self.rank & 0b111) << 2
		encoded |= (self.access_status & 0b1) << 5
		encoded |= (self.bot_mode & 0b1) << 6

		return encoded
	
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		else:
			return False
		
	def __ne__(self, other):
		return not self.__eq__(other)


class User:
	def __init__(self, userName, country = "??", cpu = 0, userID = 0, lobbyID = "stresstester client"):
		self.userName = userName
		self.country = country
		self.cpu = cpu
		self.userID = userID
		self.lobbyID = lobbyID
		self.battleID = None
		self.channels = {}
		self.state = State.LOGGEDIN # we need to be able to track other user's states too
		self.status = 0
		self.battlestatus = 0
		
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		else:
			return False
		
	def __ne__(self, other):
		return not self.__eq__(other)

class Battle:
	def __init__(self, battleID, type, natType, founder, ip, port, maxPlayers, passworded, rank, mapHash, engineName="engineName",  engineVersion= 'engineVersion',map = "map", title='title', gameName = 'gameName',  channel = 'channel'):
		self.users = {}
		self.battleID = battleID
		self.type = type
		self.natType = natType
		self.founder = founder
		self.ip = ip
		self.port = port
		self.maxPlayers = maxPlayers
		self.passworded = passworded
		self.rank = rank
		self.mapHash = mapHash
		self.engineName = engineName
		self.engineVersion = engineVersion
		self.map = map
		self.title = title
		self.gameName = gameName
		self.channel = channel
	def join(self, user):
		if user.userName in self.users:
			print(f"Battle:Join: User {user.userName} already in battle {self.battleID}")
			return False
		else:
			if user.battleID is None:
				self.users[user.userName] = user
				user.battleID = self.battleID
				return True
			else:
				print(f"Battle:Join: User {user.userName} was already in a different battle {user.battleID} when trying to join {self.battleID}")
				return False
	def leave(self, user):
		if user.userName not in self.users:
			print(f"Battle:Leave: User {user.userName} wasnt even in battle {self.battleID}")
			return False
		else:
			ok = True
			if user.battleID is None:
				print(f"Battle:Leave: User {user.userName} already had None battleid while leaveing {self.battleID}")
				ok = False
			elif user.battleID != self.battleID:
				print(f"Battle:Leave: User {user.userName} leaveing {self.battleID} had a different battleID {user.battleID}")
				ok = False
			user.battleID = None
			del self.users[user.userName]
			return ok
	
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		else:
			return False
		
	def __ne__(self, other):
		return not self.__eq__(other)

class Channel:
	def __init__(self, name):
		self.name = name
		self.users = {}
	def join(self,user):
		if user.userName in self.users:			
			print(f"Channel:Join: User {user.userName} already in channel {self.name}, members: {self.users.keys()}")
		else:
			self.users[user.userName] = user
	def leave(self, user):
		if user.userName not in self.users:
			print(f"Channel:Leave: User {user.userName} wasnt even in channel {self.name}")
		else:
			del self.users[user.userName]

	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.__dict__ == other.__dict__
		else:
			return False
		
	def __ne__(self, other):
		return not self.__eq__(other)

class LobbyClient:

	def __init__(self, server_addr, username, password, email):
		self.host_socket = None
		self.socket_data = ""

		self.username = username
		self.email = email
		self.password = password
		self.password = base64.b64encode(md5(password.encode("utf-8")).digest()).decode("utf-8")
		assert(type(self.password) == str)

		self.state = State.INIT
		self.nextstep = random.randint(0, 200)
		self.users = {}
		self.battles = {}
		self.channels = {}
		self.usertobattle = {}
		self.battleid = 0
		self.running = True
		self.handlers = {} #key name, value tuple of(function, argcount, varargcount)
		self.cmdlog = [] # push all server and client messages here 
		self.joinBattleTarget = None
		self.myUser = User(self.username)
		self.OpenSocket(server_addr)
		self.Init()

	def OpenSocket(self, server_addr):
		#ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
		#ssl_context.load_verify_locations("server.pem")

		while (self.host_socket == None):
			try:
				sock = socket.create_connection(server_addr,5)
				#ssl_context = ssl.create_default_context()
				#secure_sock = ssl_context.wrap_socket(sock, server_hostname=server_addr[0])
				## non-blocking so we do not have to wait on server
				#self.host_socket = secure_sock
				self.host_socket = sock
				self.host_socket.setblocking(0)
				print (f"{self.username} Connected")
			except socket.error as msg:
				print("[OpenSocket] %s" % msg)
				## print(traceback.format_exc())
				time.sleep(0.5)
			#print (f"Trying to connect as {self.username}")

	def Init(self):
		self.prv_ping_time = time.time()
		self.num_ping_msgs =     0
		self.max_ping_time =   0.0
		self.min_ping_time = 100.0
		self.sum_ping_time =   0.0
		self.iters = 0
		self.state = State.INIT

		self.data_send_queue = []

		self.server_info = ("", "", "", "")

		self.requested_registration   = False ## set on out_REGISTER
		self.requested_authentication = False ## set on out_LOGIN
		self.accepted_registration    = False ## set on in_REGISTRATIONACCEPTED
		self.rejected_registration    = False ## set on in_REGISTRATIONDENIED
		self.accepted_authentication  = False ## set on in_ACCEPTED

		self.out_LOGIN()

	def Cleanup(self):			
		self.host_socket = None
		self.socket_data = ""	
		self.users = {}
		self.battles = {}
		self.channels = {}
		self.usertobattle = {}

	def AssertUserNameExists(self, userName, verbose = True):
		if userName not in self.users:
			if verbose:
				curframe = inspect.currentframe()
				calframe = inspect.getouterframes(curframe, 2)
				print(f'AssertUserNameExists: {userName} does not exist, called from {calframe[1][3]}')
			return False
		else:
			return True
		
	def AssertBattleIDExists(self, battleID, verbose = True):
		if battleID not in self.battles:
			if verbose:
				curframe = inspect.currentframe()
				calframe = inspect.getouterframes(curframe, 2)
				print(f'AssertBattleIDNameExists: {battleID} does not exist, called from {calframe[1][3]}')
			return False
		else:
			return True
		
	def AssertChanNameExists(self, chanName, verbose = True):
		if chanName not in self.channels:
			if verbose:
				curframe = inspect.currentframe()
				calframe = inspect.getouterframes(curframe, 2)
				print(f'AssertChanNameExists: {chanName} does not exist, called from {calframe[1][3]}')
			return False
		else:
			return True
		
	def AssertUserIsInBattle(self, userName, battleID, verbose = True):
		# by this point assume that user and battle both exist
		user = self.users[userName]
		battle = self.battles[battleID]
		if userName not in battle.users:
			if verbose: 
				curframe = inspect.currentframe()
				calframe = inspect.getouterframes(curframe, 2)
				print(f'AssertUserIsInBattle: {userName} is not in {battleID}, called from {calframe[1][3]}')
			return False
		if user.battleID != battleID:
			if verbose: 
				curframe = inspect.currentframe()
				calframe = inspect.getouterframes(curframe, 2)
				print(f'AssertUserIsInBattle: {userName} appears to be in a different battle {user.battleID}, and not in {battleID}, called from {calframe[1][3]}')
			return False
		return True


	def Send(self, data, batch = True):
		## test-client never tries to send unicode strings, so
		## we do not need to add encode(UNICODE_ENCODING) calls
		##
		## print("[Send][time=%d::iter=%d] data=\"%s\" queue=%s batch=%d" % (time.time(), self.iters, data, self.data_send_queue, batch))
		assert(type(data) == str)

		if (len(data) == 0):
			return
		try:
			if data[0:4] != "PING":
				self.cmdlog.append(f"[{time.time():.2f}] OUT: {data} S:{self.state}")
			print(data)
			self.host_socket.send(data.encode("utf-8") + b"\n")
		except ConnectionResetError:
			print (f"Connection reset for user {self.username}") 


	def Recv(self):
		num_received_bytes = len(self.socket_data)

		try:
			self.socket_data += self.host_socket.recv(4096).decode("utf-8")
		except BlockingIOError as e:
			#print (f"BlockingIOError")
			if e.errno == 11: # Resource temporarily unavailable
				return
			return
			#raise(e)
		except ConnectionResetError as e:
			self.Cleanup()
			print(f"ConnectionResetError {self.username}")
			time.sleep(10)
			#self.Init()
		except ConnectionAbortedError as e:
			self.Cleanup()
			print(f"ConnectionResetError {self.username}")
			time.sleep(10)
			#self.Init()


		if (len(self.socket_data) == num_received_bytes):
			return

		split_data = self.socket_data.split("\n")
		data_blobs = split_data[: len(split_data) - 1  ]
		final_blob = split_data[  len(split_data) - 1: ][0]

		for raw_data_blob in data_blobs:
			if (len(raw_data_blob) == 0):
				continue
			
			## strips leading spaces and trailing carriage return
			self.Handle((raw_data_blob.rstrip('\r')).lstrip(' '))

		self.socket_data = final_blob

	def Handle(self, msg):
		## probably caused by trailing newline ("abc\n".split("\n") == ["abc", ""])
		if (len(msg) <= 1):
			return True
		
		if msg[0:4] != "PONG":
			self.cmdlog.append(f"[{time.time():.2f}] IN:  {msg} S:{self.state}")


		assert(type(msg) == str)

		numspaces = msg.count(' ')

		if (numspaces > 0):
			command, args = msg.split(' ', 1)
		else:
			command = msg
			args = ""

		command = command.upper()

		command = command.replace(".","_")

		if command not in self.handlers:
			funcname = 'in_%s' % command
			function = getattr(self, funcname)
			function_info = inspect.getfullargspec(function) # FullArgSpec(args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations)
			#print(f"Function {funcname} has {function_info.args} args and {function_info.defaults} defaults")
			required_args = 0
			if function_info.args:
				required_args = len(function_info.args) -1
			total_args = required_args
			if function_info.defaults:
				total_args += len(function_info.defaults)

			self.handlers[command] = (function, required_args, total_args) # -1 for self
		
		function, required_args, total_args = self.handlers[command]

		#if (function_info[3]):
		#	optional_args = len(function_info[3])

		#required_args = total_args - optional_args

		if (required_args == 0 and numspaces == 0):
			function()
			return True

		## bunch the last words together if there are too many of them
		if (numspaces > total_args - 1):
			arguments = args.split(' ', total_args - 1)
		else:
			arguments = args.split(' ', total_args -2)

		try:
			function(*(arguments))
			return True
		except Exception as e:
			print("Error handling: \"%s\" %s" % (msg, e))
			print(traceback.format_exc())
			return False

	def dumpLog(self,reason = ""):
		logstr = '\n'.join(self.cmdlog)
		print(f'{logstr} \n {self.username} dumped log for {reason}')
		pass

	def out_LOGIN(self):
		#self.Send("LOGIN %s %s 0 *\tstresstester client\t0\tsp cl p" % (self.username, self.password))
		self.Send("LOGIN %s %s 0 * stresstester client\t9762349872\tsp b" % (self.username, self.password))
		self.requested_authentication = True
		print (f"LOGIN {self.username}")

	def out_REGISTER(self):
		print("[REGISTER][time=%d::iter=%d]" % (time.time(), self.iters))
		self.Send("REGISTER %s %s %s" % (self.username, self.password, self.email ))
		self.requested_registration = True

	def out_CONFIRMAGREEMENT(self):
		print("[CONFIRMAGREEMENT][time=%d::iter=%d]" % (time.time(), self.iters))
		self.Send("CONFIRMAGREEMENT")


	def out_PING(self):
		#print("[PING][time=%d::iters=%d]" % (time.time(), self.iters))
		self.Send("PING")

	def out_JOIN(self, chan):
		self.Send("JOIN " + chan)
	def out_LEAVE(self, chan):
		self.Send("LEAVE " + chan)
	def out_SAY(self, chan, msg):
		self.Send("SAY %s %s" %(chan, msg))

	def out_EXIT(self):
		self.host_socket.close()

	def out_SAYPRIVATE(self, user, msg):
		self.Send("SAYPRIVATE %s %s" % (user, msg))

	def in_OPENBATTLE(self, msg):
		#print("%s Created battle %d" %(self.username, int(msg)))
		self.battleid = int(msg)

	def in_REQUESTBATTLESTATUS(self, msg):
		pass

	def out_OPENBATTLE(self, type, natType, password, port, maxPlayers, gameHash, rank, mapHash, engineName, engineVersion, map, title, gameName):
		self.state = State.JOININGBATTLE
		self.Send("OPENBATTLE %d %d %s %d %d %d %d %d %s\t%s\t%s\t%s\t%s" %
			(type, natType, password, port, maxPlayers, gameHash, rank, mapHash, engineName, engineVersion, map, title, gameName))

	def in_TASSERVER(self, protocolVersion, springVersion, udpPort, serverMode):
		print("[TASSERVER][time=%d::iter=%d] proto=%s spring=%s udp=%s mode=%s" % (time.time(), self.iters, protocolVersion, springVersion, udpPort, serverMode))
		self.server_info = (protocolVersion, springVersion, udpPort, serverMode)

	def in_SERVERMSG(self, msg):
		print("[SERVERMSG][time=%d::iter=%d][%s] %s" % (time.time(), self.iters,self.username, msg))


	def in_AGREEMENT(self, msg):
		#time.sleep(5)
		pass

	def in_QUEUED(self, msg = ""):
		print ("queued", msg)
		time.sleep(1)
		pass 

	def in_AGREEMENTEND(self):
		print("[AGREEMENTEND][time=%d::iter=%d]" % (time.time(), self.iters))
		#assert(self.accepted_registration)
		assert(not self.accepted_authentication)
		time.sleep(5)
		self.out_CONFIRMAGREEMENT()
		self.out_LOGIN()


	def in_REGISTRATIONACCEPTED(self):
		print("[REGISTRATIONACCEPTED][time=%d::iter=%d]" % (time.time(), self.iters))

		## account did not exist and was created
		self.accepted_registration = True

		## trigger in_AGREEMENT{END}, second LOGIN there will trigger ACCEPTED
		self.out_LOGIN()

	def in_REGISTRATIONDENIED(self, msg):
		print("[REGISTRATIONDENIED][time=%d::iter=%d] %s" % (time.time(), self.iters, msg))

		self.rejected_registration = True


	def in_ACCEPTED(self, msg):
		#print("[LOGINACCEPTED][time=%d::iter=%d]" % (time.time(), self.iters))

		## if we get here, everything checks out
		self.accepted_authentication = True

	def in_DENIED(self, msg):
		print("[DENIED][time=%d::iter=%d] %s" % (time.time(), self.iters, msg))

		## login denied, try to register first
		## nothing we can do if that also fails
		self.out_REGISTER()

	def in_MOTD(self, msg):
		pass

	def in_ADDSTARTRECT(self, num = "", tl = "", br = "", tr = "", bl = ""):
		pass

	def in_SAIDBATTLEEX(self, user = "", msg = "", unk1 = '', unk2 = '', unk3 = '', unk4 = '', unk5 = '', unk6 = '', unk7 = '', unk8 = '', unk9 = '', unk10 = '', unk11 = '', unk12 = '', ):
		pass

	def in_REMOVESCRIPTTAGS(self, script = '', tag = '', unk1 = "", unk2 = ""):
		pass

	def in_S_BATTLE_UPDATE_LOBBY_TITLE(self, battleid = "", newtitle = ""):
		pass

	def in_ADDUSER(self, userName, country, cpu, userID, lobbyID = "*", unused = "*"):
		user = User(userName, country, cpu, userID, lobbyID)
		self.users[userName] = user

	def in_REGISTER(self, username, password):
		pass

	def in_BATTLEOPENED(self, battleID, type, natType, founder, ip, port, maxPlayers, passworded, rank, mapHash, engineName="engineName",  engineVersion= 'engineVersion',map = "map", title='title', gameName = 'gameName',  channel = 'channel',
					  un1 = '', un2 = '', un3 = '' , un4 = '', un5 ='', un6= '', un11 = '', un12 = '', un13 = '' , un14 = '', un15 ='', un16= '', un21 = '', u22 = '', un23 = '' , un24 = '', un25 ='', un26= ''):
		#print("BATTLEOPENED received %d %s" %(battleid, self.username))
		if self.AssertUserNameExists(founder):
			if battleID in self.battles:
				print(f"in_BATTLEOPENED: {battleID} already exists in battles: {self.battles}")
			else:
				battle = Battle(battleID, type, natType, founder, ip, port, maxPlayers, passworded, rank, mapHash, engineName,  engineVersion, map , title, gameName ,  channel)		
				self.battles[battleID] = battle
				# Hosts automatically join their own battles
				#self.in_JOINEDBATTLE(battleID, founder)

	def in_UPDATEBATTLEINFO(self, msg):
		#print(msg)
		pass

	def in_JOINBATTLE(self, battleID, hashCode, chanName = ""): 
		#notifies us only!
		#but it seems like we are also sent a JOINEDBATTLE for our own battle too
		if self.AssertBattleIDExists(battleID):
			if not self.battles[battleID].join(self.users[self.username]):
				self.dumpLog()
			else:
				self.state = State.INBATTLE
		pass
		
	def in_JOINEDBATTLE(self, battleID, userName, scriptPassword = "*"):
		if self.AssertBattleIDExists(battleID) and self.AssertUserNameExists(userName):
			if self.username == userName:
				if userName not in self.battles[battleID].users:
					self.battles[battleID].join(self.users[userName])
				if self.username == self.battles[battleID].founder:
					self.state = State.HOSTING
				else:
					self.state = State.INBATTLE
			else:
				if not self.battles[battleID].join(self.users[userName]):
					self.dumpLog()
			
	def in_CLIENTSTATUS(self, msg):
		pass
	def in_LOGININFOEND(self):
		## do stuff here (e.g. "JOIN channel")
		self.state = State.LOGGEDIN
		pass

	def in_CHANNELTOPIC(self, msg):
		print("CHANNELTOPIC %s"%msg)

	def in_SETSCRIPTTAGS(self,msg):
		pass

	def in_BATTLECLOSED(self, battleID):
		if self.AssertBattleIDExists(battleID):

			#amazing fun, we could have sent a JOINBATTLE, and if the battle gets closed meanwhile, then that will 
			#never return a JOINBATTLEFAILED

			if self.state == State.JOININGBATTLE and self.joinBattleTarget == battleID:
				self.state = State.LOGGEDIN
				self.joinBattleTarget = None


			userNames = list(self.battles[battleID].users.items())
			for userName, user in userNames:
				if userName == self.username:
					self.state = State.LOGGEDIN
				if self.AssertUserNameExists(userName):
					self.battles[battleID].leave(user)
			del self.battles[battleID]
	
	def in_REMOVEUSER(self, userName):
		if self.AssertUserNameExists(userName):
			del self.users[userName]
		#print("REMOVEUSER %s" % msg)
	def in_LEFTBATTLE(self, battleID, userName):
		if self.AssertUserNameExists(userName) and self.AssertBattleIDExists(battleID) and self.AssertUserIsInBattle(userName, battleID):
			self.battles[battleID].leave(self.users[userName])
			if userName == self.username:
				self.state = State.LOGGEDIN
				# if we are the dounders of our own battle, mark it as closed?
				# now this is a very interesting one, 
				# if we are the founders, and we leave the battle, then after we leave it, a few secs later it will get closed!

		#print("LEFTBATTLE %s" % msg)

	def in_JOINBATTLEREQUEST(self, userName, ip): #sent by server to battle host
		#we should check if hes not already in some other battle, or my battle.
		mybattleID = self.users[self.username].battleID
		if self.AssertUserNameExists(userName) and self.AssertBattleIDExists(mybattleID):
			if self.users[userName].battleID is not None:
				print(f"JOINBATTLEREQUEST user {userName} asking to join my battle {mybattleID} is already in a battle at {self.users[userName].battleID}")
				self.out_JOINBATTLEDENY(userName, f"is already in a battle at {self.users[userName].battleID}")
			else:
				self.out_JOINBATTLEACCEPT(userName)

	def out_JOINBATTLEACCEPT(self, userName):
		self.Send(f"JOINBATTLEACCEPT {userName}")

	def out_JOINBATTLEDENY(self, userName, reason = ""):
		self.Send(f"JOINBATTLEDENY {userName} {reason}")

	def out_LEAVEBATTLE(self):
		self.Send(f"LEAVEBATTLE")

	def in_PONG(self):
		diff = time.time() - self.prv_ping_time

		self.min_ping_time = min(diff, self.min_ping_time)
		self.max_ping_time = max(diff, self.max_ping_time)
		self.sum_ping_time += diff
		self.num_ping_msgs += 1

		if (False and self.prv_ping_time != 0.0):
			print("[PONG] max=%0.3fs min=%0.3fs avg=%0.3fs" % (self.max_ping_time, self.min_ping_time, (self.sum_ping_time / self.num_ping_msgs)))

		self.prv_ping_time = time.time()

	def in_JOIN(self, chanName):
		if chanName in self.channels:
			print(f'in_JOIN: Channame {chanName} already exists')
		else:
			self.channels[chanName] = Channel(chanName)
		self.channels[chanName].join(self.users[self.username])
		#print("JOIN %s" % msg)

	def in_CLIENTS(self, msg):
		print("CLIENTS %s"% msg)

	def in_JOINED(self, chanName, userName): 
		# Sent to all clients in a channel (except the new client) when a new user joins the channel. 
		if self.AssertUserNameExists(userName) and self.AssertChanNameExists(chanName):
			self.channels[chanName].join(self.users[userName])
		#print(f"JOINED {chanName} {userName}")

	def in_LEFT(self, chanName, userName, reason = ""):
		if self.AssertUserNameExists(userName) and self.AssertChanNameExists(chanName):
			self.channels[chanName].leave(self.users[userName])	
		#print("LEFT %s" % msg)
			
	def in_SAID(self, msg):
		#print("SAID %s" %msg)
		pass

	def in_JOINBATTLEFAILED(self, reason):
		print(f"JOINBATTLEFAILED {self.username} {reason}")
		#self.dumpLog(reason)
		if self.state == State.JOININGBATTLE:
			self.state = State.LOGGEDIN
			self.joinBattleTarget = None

	def in_SAIDPRIVATE(self, userName, message):
		if self.AssertUserNameExists(userName):
			self.out_SAYPRIVATE(userName,"You said: " + message)

	def in_SAYPRIVATE(self, msg):
		print("SAYPRIVATE " +  msg)
	def in_OPENBATTLEFAILED(self, msg):
		pass
	def in_CLIENTBATTLESTATUS(self, msg):
		#print("CLIENTBATTLESTATUS " +msg)
		pass
	def in_FAILED(self, msg):
		#self.dumpLog(msg)
		print("FAILED " + msg)

	def HostBattle(self): # open or join a battle
		#print(self.username + " is trying to create a battle...")
		self.out_OPENBATTLE(0, 0, '*', 1234, 10, 0x1234, 0, 0x1234, "spring", "103.0", "DeltaSiegeDry", f"Game {self.username}:{self.iters}", "Balanced Annihilation V9.54")

	def JoinBattle(self): # open or join a battle
		#print(self.username + " is trying to create a battle...")
		if len(self.battles) > 0:
			battleID = random.choice(list(self.battles.keys()))
			self.out_JOINBATTLE(battleID)
			self.state = State.JOININGBATTLE
			self.joinBattleTarget = battleID

	def out_JOINBATTLE(self, battleID, password = 'empty', scriptPassword = "1234512345"):
		if scriptPassword is None:
			self.Send(f"JOINBATTLE {battleID} {password}")
		else:
			self.Send(f"JOINBATTLE {battleID} {password} {scriptPassword}")


	def PlayInBattle(self): # start game or wait till game start
		pass
	def LeaveBattle(self): # leave battle
		self.out_LEAVEBATTLE()

	def JoinChannel(self): # join channel
		self.out_JOIN("sy")
	def LeaveChannel(self): # leave channel
		self.out_LEAVE("sy")


	def Say(self):
		self.out_SAY("sy", "Hello World no. %d" %(self.iters))

	def CompareState(self, other):
		usersmatch = True
		battlelistmatch = True
		battleusersmatch = True
		for userName in sorted(list(self.users.keys())):
			if userName not in other.users:
				print(f"Mismatch between userlist between {self.username} and {other.username}: {userName} does not exist in other")
				usersmatch = False
		if not usersmatch:
			print(f"{self.username} userlist: {sorted(list(self.users.keys()))}")
			print(f"{other.username} userlist: {sorted(list(other.users.keys()))}")

		for battleID in sorted(list(self.battles)):
			if battleID not in other.battles:
				print(f"Mismatch between battlelist between {self.username} and {other.username}: {battleID} does not exist in other")
				battlelistmatch = False
			else:
				battleusersmatch = True
				for userName in self.battles[battleID].users.keys():
					if userName not in other.battles[battleID].users:
						print(f"Mismatch between battlelist between {self.username} and {other.username}: {battleID} does not have user {userName}")
						battleusersmatch = False
				if not battleusersmatch:
					usersmatch = False
					print(f"{self.username} battleID {battleID}: {sorted(list(self.battles[battleID].users.keys()))}")
					print(f"{other.username} battleID {battleID}: {sorted(list(other.battles[battleID].users.keys()))}")
		if not battlelistmatch:
			print(f"{self.username} battlelist: {sorted(list(self.battles.keys()))}")
			print(f"{other.username} battlelist: {sorted(list(other.battles.keys()))}")
			

		return battlelistmatch and usersmatch



	def Update(self, step = True):
		assert(self.host_socket != None)

		if step:
			self.iters += 1

			if ((self.iters % 10) == 0):
				self.out_PING()


			if (self.iters > self.nextstep):
				self.nextstep = self.iters + random.randint(1, 2)

				if self.state == State.LOGGEDIN:
					if random.random() < 0.1:
						self.HostBattle()
					else:
						self.JoinBattle()
				elif self.state == State.HOSTING:
					#dunno, kick people randomly?
					if random.random() < 0.01:
						self.LeaveBattle()
					else:
						pass
				elif self.state == State.INBATTLE:
					if random.random() < 0.2:
						self.LeaveBattle()
					else:
						pass

		## eat through received data
		self.Recv()

	def Run(self, iters):
		for i in range(iters):
			self.Update()
			time.sleep(0.2)
		time.sleep(1)
		self.Update(step = False)

		## say goodbye and close our socket
		self.out_EXIT()

def CompareClients(clients):
	identities = [[]]  # of dicts of identities
	identities[0].append(clients.pop(0))

	allmatch = True
	for i, client in enumerate(clients):
		unique = True
		for cluster in identities:
			other = cluster[0]
			if client.CompareState(other) and other.CompareState(client):
				unique = False
				cluster.append(client)
				break
		if unique:
			identities.append([client])

	print(f'Sizes of individual clusters for {len(clients)} is {",".join([len(cluster)for cluster in identities])}')

	if len(identities) > 1:
		print(f"Clients dont match after {NUM_UPDATES} updates")
	else:
		print(f"Clients match after {num_updates} updates")
	return  len(identities) == 1


def RunClients(num_clients, num_updates):
	clients = [None] * num_clients

	for i in range(num_clients):
		#clients[i] = LobbyClient(HOST_SERVER, (CLIENT_NAME % i), (CLIENT_PWRD % i))
		clients[i] = LobbyClient(HOST_SERVER, (CLIENT_NAME % i), (CLIENT_PWRD), (CLIENT_EMAIL % i))

	for j in range(num_updates):
		if j == num_updates -1 :
			time.sleep(1)
			for i in range(num_clients):
				clients[i].Update(step = False)
		else:

			for i in range(num_clients):
				clients[i].Update()
		time.sleep(0.1)

	CompareClients(clients)

	for i in range(num_clients):
		clients[i].out_EXIT()

class ClientThread(threading.Thread):
	def __init__(self, args):
		threading.Thread.__init__(self)
		self.client = None
		self.client_num = args[0]
		self.num_updates = args[1]
	def run(self):

		#client = LobbyClient(HOST_SERVER, (CLIENT_NAME % self.client_num), (CLIENT_PWRD % self.client_num))
		client = LobbyClient(HOST_SERVER, (CLIENT_NAME % self.client_num), (CLIENT_PWRD ),  (CLIENT_EMAIL % self.client_num ))

		print("[RunClientThread] running client %s" % client.username)
		client.Run(self.num_updates)
		print("[RunClientThread] client %s finished" % client.username)
		self.client = client
		return client
	
	

def RunClientThread(i, k):
	client = LobbyClient(HOST_SERVER, (CLIENT_NAME % i), (CLIENT_PWRD % i),  (CLIENT_EMAIL % i))

	print("[RunClientThread] running client %s" % client.username)
	client.Run(k)
	print("[RunClientThread] client %s finished" % client.username)
	return client

def RunClientThreads(num_clients, num_updates):
	threads = [None] * num_clients
	clients = []
	for i in range(num_clients):
		#threads[i] = threading.Thread(target = RunClientThread, args = (i, num_updates, ))
		threads[i] = ClientThread( (i, num_updates ))
		threads[i].start()
	for i,t in enumerate(threads):
		t.join()
		clients.append( t.client)
	CompareClients(clients)


def main():
	if USE_THREADS:
		RunClientThreads(NUM_CLIENTS, NUM_UPDATES)
	else:
		RunClients(NUM_CLIENTS, NUM_UPDATES)

if __name__ == "__main__":
	main()

