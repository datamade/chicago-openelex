import os
import json
import datetime
import probablepeople as pp

from openelex.models import RawResult

STATE = 'IL'
PLACE = 'Chicago'

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
				name, seat, raw_date = parts
				name_party = None
			elif len(parts) == 4:
				name, seat, name_party, raw_date = parts

			if 'primary' in name.lower():
				election_type = 'primary'
			else:
				election_type = 'general'

		else:
			special = False

			if len(parts) == 2:
				name, raw_date = parts
				name_party = None
			elif len(parts) == 3:
				name, name_party, raw_date = parts

			if 'general' in name.lower() or 'geeral' in name.lower():
				election_type = 'general'
			elif 'primary' in name.lower():
				election_type = 'primary'
			elif 'runoff' in name.lower():
				election_type = 'runoff'
			else:
				election_type = None

		if 'municipal' in name.lower():
			municipal = True
		else:
			municipal = False

		raw_date = raw_date.strip()
		try:
			elec_date = datetime.datetime.strptime(raw_date, '%m/%d/%y')
		except:
			elec_date = datetime.datetime.strptime(raw_date, '%m/%d/%Y')

		elec_metadata = {
			'filename': filename,
			'raw_date': raw_date,
			'name': name,
			'election_type': election_type,
			'special': special,
			'municipal': municipal,
			'party': name_party,
			'start_date': elec_date,
			'end_date': elec_date, # when would start date be diff from end date?
		}

		print "loading election:", election_name

		return elec_metadata

class ChicagoLoader():

	def load(self, elec_metadata):

		chicago_args = {
			'created': datetime.datetime.now(),
			'updated': datetime.datetime.now(),
			'source': elec_metadata['filename'],
			'election_id': self.make_election_id(elec_metadata), # change this
			'state': STATE,
			'place': PLACE,
			'start_date': elec_metadata['start_date'],
			'end_date': elec_metadata['end_date'],
			'election_type': elec_metadata['election_type'],
			'result_type': 'certified',
		}

		results = []

		# loop through json, do stuff to add to kwargs
		with open('election_json/'+elec_metadata['filename']) as f:
			content = f.read()
			election_json = json.loads(content)

			seen_ballot_measure = False
			for contest in election_json['contests']:

				# for chicago election results, contests are always listed
				# offices first, then judges, then ballot measures.
				# since judges (which are sometimes just a name) & ballot initiatives
				# don't have any language marking them as such, get_contest_args
				# will use a name parser to identify a string as a name (therefore a judge) 
				# or not a name (therefore a ballot measure). once one ballot measure is seen,
				# the rest of the contests for that election are ballot measures
				is_ballot_measure, contest_args = self.get_contest_args(chicago_args, contest['position'], seen_ballot_measure)
				if is_ballot_measure:
					seen_ballot_measure = True

				if contest_args:
					# print "   loading contest:", contest['position']
					contest_results = self.make_results(contest_args, contest['results'])
					results.extend(contest_results)
				else:
					print "   contest not loaded:", contest['position']

		if results:
			RawResult.objects.no_cache().insert(results)

	def make_election_id(self, elec_metadata):
		d = elec_metadata['start_date'].strftime('%Y-%m-%d')
		if elec_metadata['municipal']:
			election_id = '%s-%s-%s-%s' %(STATE.lower(), PLACE.lower(), d, elec_metadata['election_type'])
		else:
			election_id = '%s-%s-%s' %(STATE.lower(), d, elec_metadata['election_type'])

		return election_id

	def get_contest_args(self, chicago_args, position, seen_ballot_measure):
		
		# load known offices
		# detect judge races & ballot initiatives

		known_offices = [
			# national
			'president of the united states',
			'president and vice president of the united states',
			'pres and vice pres',
			'president, u.s.',
			'senator, u.s.',
			'united states senator',
			'u.s. senator',
			'u.s. representative',
			'representative in congress',
			'rep. in congress',

			# state
			'governor',
			'lieutenant governor',
			'governor & lieutenant governor',
			'governor and lieutenant governor',
			'secretary of state',
			'attorney general',
			'state\'s attorney',
			'comptroller',
			'treasurer',
			'state senator',
			'state representative',
			'rep. in general assembly',
			'rep. in gen. assembly',

			# county
			'commissioner',
			'board president',
			'president cook county board comm',
			'clerk',
			'sheriff',
			'treasurer',
			'assessor',
			'commissioner, county board',
			'board of review',
			'recorder of deeds',

			'supreme court',
			'appellate court',
			'apellate court',
			'judge, cook county circuit',
			'circuit court',
			'circuit couut',
			'subcircuit',

			# city
			'mayor',
			'alderman',
			'committeeman',
		]

		offices_to_skip = [
			'ballots cast',
			'registered voters',
			'amendment',
			'national convention',
			'natl. convention',
			'delegate natl',
			'delegates natl',
			'state central committeeman',
			'state central',
		]

		chicago_args['office'] = position.lower()

		for office_substring in offices_to_skip:
			if office_substring in position.lower():
				return None, None

		for office_substring in known_offices:
			if office_substring in position.lower():
				is_ballot_measure = False
				if 'retain' in position.lower():
					chicago_args['is_retention'] = True
				return is_ballot_measure, chicago_args

		if not seen_ballot_measure:
			# at this point, an office is none of the above
			try:
				tokens, name_type = pp.tag(position.lower())

				if name_type == 'Person':
					chicago_args['is_retention'] = True
					is_ballot_measure = False
					return is_ballot_measure, chicago_args
				else:
					chicago_args['is_ballot_measure'] = True
					is_ballot_measure = True
					return is_ballot_measure, chicago_args
			except pp.RepeatedLabelError:
				print "REPEATED LABEL ERROR"
				return None, None

		else:
			chicago_args['is_ballot_measure'] = True
			is_ballot_measure = True
			return is_ballot_measure, chicago_args



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

