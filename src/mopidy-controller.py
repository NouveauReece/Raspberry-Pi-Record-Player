import re
import os
import sys
import time
import RPi.GPIO as GPIO
import serial
import subprocess
import requests
from playsound import playsound
import alsaaudio
import signal

# Audio mixer
Mixer = alsaaudio.Mixer()
# Initial audio
Volume = 50

# Supported commands
commands = {
	"play" 		: lambda x: {"method" : "core.playback.play", "params" : {}},
	"pause" 	: lambda x: {"method" : "core.playback.pause", "params" : {}},
	"next" 		: lambda x: {"method" : "core.playback.next", "params" : {}},
	"prev" 		: lambda x: {"method" : "core.playback.previous", "params" : {}},
	"stop" 		: lambda x: {"method" : "core.playback.stop", "params" : {}},
	"add" 		: lambda x: {"method" : "core.tracklist.add", "params" : {"uris" : [x]}},
	"clear" 	: lambda x: {"method" : "core.tracklist.clear", "params" : {}},
	"shuffle" 	: lambda x: {"method" : "core.tracklist.shuffle", "params" : {}},
}

def convert_spotify_url(url):
	# Spotify regex for correct URI with 22 character Spotify id
	spotify_id_regex = "^(https://open\.spotify\.com)/(album|track|playlist|episode|show)/[0-9a-zA-Z]{22}$"
	# Incorrect format
	if not re.match(spotify_id_regex, url):
		raise ValueError("Incorrect spotify uri encoding.")
	# Spit uri into sections
	sections = url[25:].split("/")
	# Return spotify api URI e.g. "spotify:track:2AED..."
	return f"spotify:{sections[0]}:{sections[1]}"

def make_request(method, params={}):
	# Setup headers
	headers = {
		'Content-Type': 'application/json',
	}
	# Setup json_data
	json_data = {
		'jsonrpc' : '2.0',
		'id' : 1,
		'method' : method,
		'params' : params,
	}
	# Mopidy post request
	res = requests.post("http://localhost:6680/mopidy/rpc", json=json_data, headers=headers)
	return res

def sound_notify(sound):
	# Stop track
	send_message(commands["stop"])
	# Set volume to a good notification sound
	Mixer.setvolume(75)
	# Play notification
	playsound("sounds/"+sound)
	# Reset volume
	Mixer.setvolume(Volume)
	# Replay track if notification was good
	if sound == "affirmative.mp3": send_message(commands["play"])

def send_message(message, url=""):
	spotify_uri = ""
	url = url.split("?")[0]
	# Check url to see if it is a valid sptofiy url
	if len(url) > 0:
		try:
			spotify_uri = convert_spotify_url(url)
		except:
			print("Incorrect spotify url")
			sound_notify("error.mp3")
			return
	# Get command dict
	cmd = message(spotify_uri)
	# Make request
	res = make_request(cmd["method"], cmd["params"])
	# User add a track and url was valid format but not a real spotify url
	if url != "" and res.json()['result'] == []:
		print("Incorrect spotify url")
		sound_notify("error.mp3")
		return
	# User added a track and it was valid
	elif url != "":	sound_notify("affirmative.mp3")
	print("Done sending message")

def get_playback_state():
	# Request state from mopidy server
	return make_request("core.playback.get_state").json()['result']


def main(mode=None):
	global Volume
	# Set volume to base volume
	Mixer.setvolume(Volume)
	send_message(commands["clear"])
	# Wait until user types in a mode
	# only used in development mode
	while mode != "ino" and mode != "terminal":
		mode = input("Enter mode [ino/terminal]: ").lower()
	# Shell development mode
	if mode == "terminal":
		while True:
			command = input("\nEnter command: ")
			url = ""
			if command.lower() == "q": break
			if command.lower() == "add": url = input("Enter spotify url: ")
			# Invalid command
			if command not in commands:
				print("Not a valid command!")
				continue
			send_message(commands[command], url)
	# Arduino mode
	elif mode == "ino":
		print("Arduino Mode")
		# Set up arduino serial port
		ser = serial.Serial("/dev/ttyACM0", 9600)
		ser.baudrate=9600
		# Arduino communication loop
		while True:
			# Read line from arduino
			read_ser = str(ser.readline())
			# Clean up string
			read_ser = read_ser[2:len(read_ser)-5]
			print(read_ser)
			# Play or pause
			if read_ser == "play/pause":
				# Get playback state
				playback_state = get_playback_state()
				# Switch state to play or pause
				if playback_state == "playing": send_message(commands["pause"])
				else: send_message(commands["play"])
			# Next
			if read_ser == "next":
				send_message(commands["next"])
			# Previous
			elif read_ser == "prev":
				send_message(commands["prev"])
			# Volume Up
			elif read_ser == "up":
				Volume = min(100, Volume+10)
				Mixer.setvolume(Volume)
			# Volume Down
			elif read_ser == "down":
				Volume = max(0, Volume-10)
				Mixer.setvolume(Volume)
			# Shuffle
			elif read_ser == "shuffle":
				send_message(commands["shuffle"])
			# Sptotify uri
			else:
				try:
					# Check if the uri is correct
					convert_spotify_url(read_ser.split("?")[0])
					# Clear tracklist
					send_message(commands["clear"])
					# Add new song
					send_message(commands["add"], read_ser)
				except Exception:
					print("Exception")
			time.sleep(.1)



if __name__ == "__main__":
	try:
		# Startup server
		process = subprocess.Popen("mopidy", shell=True)
		# Keep sending a request to server until it is awake
		while True:
			print("\033[33mChecking connection\033[39m")
			try:
				time.sleep(1)
				get_playback_state()
				break
			except Exception:
				pass
		# Notify user that everything is set up and ready to go
		Mixer.setvolume(75)
		playsound("sounds/startup.mp3")
		# Run the mian loop in arduino mode
		main("ino")
	except KeyboardInterrupt:
		# User terminated the process
		print("\nGoodbye!\n")
		# Kill server
		os.kill(process.pid, signal.SIGINT)
		time.sleep(3)
		# Notify user that they can unplug device
		Mixer.setvolume(75)
		playsound("sounds/shutdown.mp3")
		# Exit
		try:
			sys.exit(130)
		except SystemExit:
			os._exit(130)
