import os
import json
import datetime

from openelex.models import RawResult


class LoadResults(object):
	"""
	Entry point for data loading.

	Determines appropriate loader for file and triggers load process.
	"""

	def run(self):

		json_files = os.listdir('election_json')

		for json_file in json_files:
			with open('election_json/'+json_file) as f:
				content = f.read()
				election_json = json.loads(content)
				elec_metadata = self.make_elec_metadata(election_json['election_name'], json_file)
			
			loader = ChicagoLoader()
			loader.load(elec_metadata)

	# metadata that we gather from the filename & the election name
	def make_elec_metadata(self, election_name, filename):
		parts = election_name.split(' - ')


		if 'special' in parts[0].lower():
			special = True

			if len(parts) == 3:
				name, seat, date = parts
				name_party = None
			elif len(parts) == 4:
				name, seat, name_party, date = parts

			if 'primary' in name.lower():
				election_type = 'primary'
			else:
				election_type = 'general'

		else:
			special = False

			if len(parts) == 2:
				name, date = parts
				name_party = None
			elif len(parts) == 3:
				name, name_party, date = parts

			if 'general' in name.lower():
				election_type = 'general'
			elif 'primary' in name.lower():
				election_type = 'primary'
			elif 'runoff' in name.lower():
				election_type = 'runoff'
			else:
				election_type = None

		elec_metadata = {
			'filename': filename,
			'date': date.strip(),
			'name': name,
			'election_type': election_type,
			'special': special,
			'party': name_party,
		}

		print "loading election:", election_name

		return elec_metadata

class ChicagoLoader():

	def load(self, elec_metadata):

		chicago_args = {
			'created': datetime.datetime.now(),
			'updated': datetime.datetime.now(),
			'source': elec_metadata['filename'],
			'election_id': elec_metadata['filename'], # change this
			'state': 'IL',
			'start_date': datetime.datetime.strptime(elec_metadata['date'], '%m/%d/%y'),
			'end_date': datetime.datetime.strptime(elec_metadata['date'], '%m/%d/%y'), # when would start date be diff from end date?
			'election_type': elec_metadata['election_type'],
			'result_type': 'certified',
		}

		results = []

		# loop through json, do stuff to add to kwargs
		with open('election_json/'+elec_metadata['filename']) as f:
			content = f.read()
			election_json = json.loads(content)

			for contest in election_json['contests']:

				contest_args = self.get_contest_args(chicago_args, contest['position'])

				if contest_args:
					print "   loading contest:", contest['position']
					contest_results = self.make_results(contest_args, contest['results'])
					results.extend(contest_results)
				else:
					print "   contest not loaded:", contest['position']

		if results:
			RawResult.objects.insert(results)

	def get_contest_args(self, chicago_args, position):

		office_mappings = {
			'senator': 'US Senator',
			'governor': 'Governor & Lieutenant Governor',
			'attorney general': 'Attorney General',
			'secretary of state': 'Secretary of State',
			'comptroller': 'Comptroller',
			'treasurer, state of illinois': 'Treasurer',
		}

		office = None
		for office_substring in office_mappings:
			if office_substring in position.lower():
				office = office_mappings[office_substring]

		if office:
			chicago_args['office'] = office
			return chicago_args
		else:
			return None

	def make_results(self, contest_args, results):

		raw_result_list = []
		for result in results:

			result_jurisdiction = "ward %s" % result['ward']
			# TO DO: add "ocd_id"

			# adding ward results
			for candidate in result['candidate_totals']:
				result_args = {
					'full_name': candidate,
					'votes': result['candidate_totals'][candidate],
					'reporting_level': 'municipal_district',
					'jurisdiction': result_jurisdiction,
				}
				result_args.update(contest_args)
				raw_result_list.append(RawResult(**result_args))

			# adding precinct results
			for precinct_result in result['results_by_precinct']:

				result_jurisdiction = "ward %s precinct %s" %(result['ward'], precinct_result['precinct'])
				# TO DO: add "ocd_id"

				for candidate in precinct_result['candidate_totals']:
					result_args = {
						'full_name': candidate,
						'votes': precinct_result['candidate_totals'][candidate],
						'reporting_level': 'precinct',
						'jurisdiction': result_jurisdiction,
					}

				result_args.update(contest_args)
				raw_result_list.append(RawResult(**result_args))

		return raw_result_list




