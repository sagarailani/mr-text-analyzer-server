from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

import os, io
from spellchecker.spellchecker import SpellChecker, Verbosity
from speechtotext.speechtotext import transcribe

@app.route('/')
def hello_world():
	return "Hello World!!"

@app.route('/spellchecker/', methods=["POST"])
@cross_origin()
def spellchecker():
	initial_capacity = 83000
	max_edit_distance_dictionary = 2
	prefix_length = 7
	data = request.get_json()
	text = data['text']
	spellcheck = SpellChecker(initial_capacity, max_edit_distance_dictionary, prefix_length)

	dictionary_path = os.path.join("/home/sagar/Projects/mr-text-analyzer-server/spellchecker", "frequency_dictionary.txt")
	term_index = 0
	count_index = 1
	if not spellcheck.load_dictionary(dictionary_path, term_index, count_index):
		return "Error"
	
	suggestions = spellcheck.lookup_compound(text, max_edit_distance_dictionary)
	corrections = dict()		
	for suggestion in suggestions:		
		corrections['text'] = suggestion.term
	return jsonify(corrections)

# @app.route('/speech-to-text/', methods=["POST"])
# @cross_origin()
# def speechToText():
# 	print("Printing some data")
# 	audioFile = request.files['audioFile']
# 	file = audioFile.read()
# 	print(type(file))
# 	text = transcribe(file)
# 	print(text)
# 	return text