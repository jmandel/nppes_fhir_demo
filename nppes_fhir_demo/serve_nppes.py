from flask import Flask, jsonify, render_template, request
import elasticsearch
import json

#creates WSGI entry point for gunicorn
app = Flask(__name__)
es = ""
 

#starting point for FHIR Practivtioner demo - yields the search form
@app.route('/nppes_fhir')
def nppes_fhir():
	return render_template('fhir_index.html') 

#old version, pre-FHIR - no longer used
@app.route('/nppes/lookup', methods=['GET'])
def lookup():
	queryText = request.args.get('queryText')
	#print "got queryText = ", queryText
	try:
		es_reply = es.search(index='nppes', default_operator="AND", size=50, q=queryText)
	except:
		print "FAILED to query ES "
		raise
	#print "es reply = ", es_reply
	data = ""
	#print es_reply
	total = es_reply['hits']['total']
	time = es_reply['took']
	hits = es_reply['hits']['hits']
	#print total, time
	#print "hits = ", hits
	providers = []
	for h in hits:
		a_doc = []
		src = h['_source']
		a_doc.append(src['firstname'])
		a_doc.append(src['lastname'])
		a_doc.append(src['credential'])		
		a_doc.append(src['mail_address_1'] + " " + \
					 src['mail_address_2'] + " " + \
					 src['city'] + " " + \
					 src['state_abbrev'])
		#a_doc.append(src['city'])
		#a_doc.append(src['state_abbrev'])
		a_doc.append(src['lastname'] + "@direct.somehisp.com")
		a_doc.append(src['spec_1'])
		a_doc.append(src['spec_2'])		
		providers.append(a_doc)

	return jsonify({'hits':total, 'time':time, 'data': providers})

#FHIR Practitioner search service
@app.route('/nppes/Practitioner', methods=['GET'])
def fhir_lookup():
	#only supports these FHIR fields for demo
	family        = request.args.get('family').strip()
	given         = request.args.get('given').strip()
	address       = request.args.get('address')	.strip()
	qualification = request.args.get('qualification').strip()
	specialty     = request.args.get('specialty').strip()

	queryText = ""
	wildcard = "*"  #lucene wildcard is applied to some of the search parameters

	#build a Lucene query string - see Lucene documentation for syntax
	if family:        queryText += "lastname:"     + family    + wildcard + "^4" + " "
	if given:         queryText += "firstname:"    + given     + wildcard + " "
	if address:
		#apply wildcard to each part of whatever user entered (street, city, state code)
		for term in address.split():       
			queryText += "full_address:" + term + wildcard + " "
	if qualification: queryText += "credential:"   + qualification        + " "
	if specialty:
		specText = ""
		#allow for either spec_1 OR spec_2 to qualify.  Everything else is an AND
		for term in specialty.split():
			specText += "spec_1:" + term + wildcard + " OR " + "spec_2:" + term + wildcard + " OR "

		queryText +=  " (" + specText[:-3] + ")"

	print "generated Lucene query = ", queryText #debug
	
	#invoke ElasticSearch usign the "lucene query mode"
	#for demo, just fetch first 50 matches.  Need to convert this to "paging" model at some point!
	try:
		es_reply = es.search(index='nppes', default_operator="AND", size=50, q=queryText)
	except:
		print "FAILED to query ES "
		raise
	#print "es reply = ", es_reply
	
	data = ""
	total = es_reply['hits']['total']  #total matches
	time = es_reply['took']		#milliseconds of ES time

	#get root of results
	hits = es_reply['hits']['hits']
	providers = []
	for h in hits:
		src = h['_source']
		a_doc = convert_to_Practitioner(src)
		providers.append(a_doc)

	#This is not really a legal FHIR return.  But it's close enough for demo
	return jsonify({'hits':total, 'time':time, 'data': providers})


#utility routines
def convert_to_Practitioner(es_provider_doc):
	#convert the results of an ES match to FHIR Practitioner record format (JSON)
	#build with python structures and then JSONify
	#this is a total hack approach.  proof of concept with lots of gaps!
	prac = {}
	prac['resourceType'] = "Practitioner"
	prac['id'] = es_provider_doc['npi'],
	prac['identifier'] = [{	
			'use':"official",
			#'type': { 'coding' : [ {'system': "NPI", 'code': "??", 'text':"NPI" }]},
			'system': "URI-for-NPI",
			'value': es_provider_doc['npi'],
		}],
	prac['name'] = {
			"use": "official",
			"family": [ es_provider_doc['lastname'] ],
			"given": [ es_provider_doc['firstname'] ],
			"suffix": [ es_provider_doc['credential'] ]
		}
	prac['gender'] = "unknown"
	address_line = es_provider_doc['mail_address_1']
	if es_provider_doc['mail_address_2']:
		address_line += "<br>" + es_provider_doc['mail_address_2']
	prac['address'] = { 
			"use": "work",
			"line": [ address_line ],
			"city": es_provider_doc['city'],
			"state": es_provider_doc['state_abbrev'],
			"country": "USA"
		}
	prac['telecom'] = [{
			"system": "Direct",
			"value": es_provider_doc['lastname'] + "@direct.somehist.com",
			"use": "work"
		}]

	if es_provider_doc['spec_1']:
		prac['practitionerRole'] = [{
				#"role": {},
				"specialty": [
				  {
					"coding": [{
						"system": "??",
						"code": "??",
						"display": es_provider_doc['spec_1']
					}],
					"text": es_provider_doc['spec_1']
				  }]
			}]
	if es_provider_doc['spec_2']:
		prac['practitionerRole'][0]['specialty'].append(
				 {
					"coding": [{
						"system": "??",
						"code": "??",
						"display": es_provider_doc['spec_2']
					}],
					"text": es_provider_doc['spec_2']
				 }
			)

	return prac


#main program here

try:
	#connect to ElasticSearch, use all defaults
	es = elasticsearch.Elasticsearch()
	print "connected to ES"
except:
	print "FAILED to connect to ES "
	raise

#if called locally (without gunicorn) then run on localhost port 5000 for debugging
#otherwise, gunicorn will invoke the "app" entrypoint for WSGI conversation
if __name__ == '__main__':
	app.run(host="127.0.0.1", port=5000, debug=True)
