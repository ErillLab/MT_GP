"""Organism Factory creates organisms, connectors and pssms
   It performs all operations dealing with multiple objects, 
   such as organism recombination.
"""

import random
import json
import numpy as np
from .organism_object import OrganismObject
from .connector_object import ConnectorObject
from .pssm_object import PssmObject
from .aligned_organisms_representation_object import AlignedOrganismsRepresentation
import copy

class OrganismFactory:
    """Factory class
    """

    def __init__(self, conf_org, conf_org_fac, conf_con, conf_pssm) -> None:
        """Instantiates an OrganismFactory object.
           Reads in the configuration paramaters for the factory and
           for all object types (organism, connector and PSSM recognizer)
        """
        self._id = 0
        
        # lambda parameter for Poisson distribution that will instantiate
        # organism. lambda is the expected number of recognizers in the
        # organism (and also its variance)
        self.num_recognizers_lambda_param = conf_org_fac[
            "NUM_RECOGNIZERS_LAMBDA_PARAM"
        ]

        self.recombination_probability = conf_org_fac["RECOMBINATION_PROBABILITY"]
        # minimum and maximum values allowed for connector mu's
        self.min_mu = conf_org_fac["MIN_MU"]
        self.max_mu = conf_org_fac["MAX_MU"]

        # minimum and maximum values allowed for connector sigma's
        self.min_sigma = conf_org_fac["MIN_SIGMA"]
        self.max_sigma = conf_org_fac["MAX_SIGMA"]
        
        # length of PSSM's
        self.pwm_length = conf_org_fac["PWM_LENGTH"]
        
        # PSSM object probability parameters
        self.pwm_probability_step = conf_org_fac[
            "PWM_PROBABILITY_STEP"
        ]  # It should be a BASE_PROBABILITY divisor Ex: 1, 2, 4, 5, 10, 25...
        self.pwm_probability_base = conf_org_fac["PWM_PROBABILITY_BASE"]
        self.pwm_probability_decimals = conf_org_fac[
            "PWM_PROBABILITY_DECIMALS"
        ]

        # assign organism, connector and pssm configurations
        self.conf_org = conf_org
        self.conf_con = conf_con
        self.conf_pssm = conf_pssm

    def get_id(self) -> int:
        """Gives a new ID for an organism
        TODO: This should be a function so all the count of IDs, including
        assigned outside the class, keep consistency between all organisms

        Returns:
           a new non-repeated ID
        """
        self._id += 1
        return self._id

    def get_organism(self) -> OrganismObject:
        """It creates and returns a full organism datastructure
           An organism contains essentially two lists:
           - a recognizer list
           - a connector list
           The placement of these elements in the lists defines
           implicitly the connections between the elements.

        Returns:
            A new organism based on JSON config file
        """
        
        # instantiates organism with organism configuration and pssm columns
        new_organism = OrganismObject(self.get_id(), self.conf_org, self.conf_pssm["MAX_COLUMNS"])
        
        # The number of recognizers of the organism is randomly chosen from a
        # Poisson distribution with the lambda provided.
        # The Poisson distribution is truncated to integers larger than 0, so
        # that null organisms are avoided. The truncation is achieved by using
        # lambda - 1 instead of lambda (in this way the average number of
        # recognizers will be lower by one unit) and then shifting up the
        # values by one unit.
        number_of_recognizers = np.random.poisson(self.num_recognizers_lambda_param - 1)
        number_of_recognizers += 1
        
        # avoid signle PSSM case, which breaks recombination operator, that 
        # assumes at least one connector is present
        if number_of_recognizers == 1:
            number_of_recognizers += 1
        
        # for each recognizer in the organism
        for i in range(number_of_recognizers - 1):
            # instantiate new recognizer and append it to organism's recognizer list
            new_recognizer = self.create_pssm(self.pwm_length)
            new_organism.recognizers.append(new_recognizer)
            # instantiate new connector and append it to organism's connector list
            _mu = random.randint(self.min_mu, self.max_mu)
            _sigma = random.randint(self.min_sigma, self.max_sigma)
            new_connector = ConnectorObject(_mu, _sigma, self.conf_con)
            new_organism.connectors.append(new_connector)
        # insert last recognizer in the chain and add it to list
        new_recognizer = self.create_pssm(self.pwm_length)
        new_organism.recognizers.append(new_recognizer)
        # Set attribute that will map organism nodes to alignment matrix rows
        new_organism.set_row_to_pssm()

        return new_organism
    
    def create_connector(self) -> ConnectorObject:
        """It returns a connector object with its internal parameters (mu, sigma)
        assigned
        """

        # Assign a random value to mu and sigma
        _mu = random.randint(self.min_mu, self.max_mu)
        _sigma = random.randint(self.min_sigma, self.max_sigma)

        # Create the new connector
        new_connector = ConnectorObject(_mu, _sigma, self.conf_con)

        return new_connector

    def create_pssm(self, length = None) -> PssmObject:
        """It return a PSSM object with a specific length

        Args:
            length: length (columns) of the PSSM
            if None, the default self.pwm_length value is used

        Returns:
            A pssm object with an initializated PWM
        """
        if length == None:
            length = self.pwm_length
        
        pwm = []
        # Generate as many PSSM columns as needed
        for _ in range(length):
            pwm.append(self.get_pwm_column())

        return PssmObject(np.array(pwm), self.conf_pssm)

    def get_pwm_column(self) -> dict:
        """Generates a single column for a PWM

        Returns:
            a random probability for each base [a, c, g, t]
        """
        
        # set initial probability to base/step
        # e.g. 100/5 emulates a motif with 20 binding sites
        initial_probability = (
            self.pwm_probability_base / self.pwm_probability_step
        )
        probabilities: list = []

        # Number of decimals on the probability
        decimals = self.pwm_probability_decimals
        # amount of probability left
        probability_left = initial_probability
        # we assign number of sites to each row, making sure that no row
        # gets less than one site
        for item in range(3,-1,-1):
            if probability_left > item:
                new_probability = random.randint(1, probability_left-item)
                probability_left -= new_probability
            else:
                new_probability = 1
                probability_left -= new_probability
            probabilities.append(new_probability)
        # if there is any remaining probability unassigned, assign to last
        if probability_left>0:
            probabilities[3] += probability_left

        # Shuffle list so high probability is not always on first positions
        random.shuffle(probabilities)            

        # Transform probabilities array from integer
        # [0-(BASE_PROBABILITY / STEP)] to complementary float
        # probabilities [0.0-1.0]
        np_probabilities = (
            np.array(probabilities)
            * self.pwm_probability_step
            * (1 / self.pwm_probability_base)
        )
        probabilities = np_probabilities.tolist()
            
        
        # # Left probability is the amount of probability left
        # left_probability = initial_probability
        # # Minimum and maximum number of probabilities to be generated
        # min_probability = 0
        # max_probability = 4
        # # Number of decimals on the probability
        # decimals = 2
        # # Generate 4 random probabilities out of initial_probability, one for
        # # each base

        # # Add a probability while we have less than 3 and and total probability
        # # is not 1
        # while (
        #         left_probability > min_probability
        #         and len(probabilities) < max_probability - 1
        # ):
        #     new_probability = random.randint(0, left_probability)
        #     probabilities.append(float(new_probability))
        #     left_probability -= new_probability
        # # Add the last probability or fill with 0 probability
        # if left_probability > 0:
        #     probabilities.append(initial_probability - sum(probabilities))
        # else:
        #     while len(probabilities) < max_probability:
        #         probabilities.append(0.0)

        # # Shuffle the array is needed so high probability is not always on
        # # first positions
        # random.shuffle(probabilities)

        # # Transform probabilities array from integer
        # # [0-(BASE_PROBABILITY / STEP)] to complementary float
        # # probabilities [0.0-1.0]
        # np_probabilities = (
        #     np.array(probabilities)
        #     * self.pwm_probability_step
        #     * (1 / self.pwm_probability_base)
        # )
        # probabilities = np_probabilities.tolist()

        # Return object with "decimals" decimals probability to each base
        return {
            "a": round(probabilities[0], decimals),
            "g": round(probabilities[1], decimals),
            "c": round(probabilities[2], decimals),
            "t": round(probabilities[3], decimals),
        }
    
    def import_organisms(self, file_name: str) -> list:
        """Import Organisms from file

        Args:
            file_name: Name of the file with the organisms to read as an input

        Returns:
            a list of organisms objects read from the file
        """
        organism_list = []

        with open(file_name) as json_file:
            organism_json = json.load(json_file)

        for organism in organism_json:

            new_organism = OrganismObject(
                self.get_id(), self.conf_org, self.conf_pssm["MAX_COLUMNS"]
            )
            
            new_org_recognizers = []  # The recognizers are collected here
            new_org_connectors = []  # The connectors are collected here
            
            for element in organism:
                if element["objectType"] == "pssm":
                    new_org_recognizers.append(self.import_pssm(element))
                elif element["objectType"] == "connector":
                    new_org_connectors.append(self.import_connector(element))
            
            # Set recognizers and connectors of the organism
            new_organism.set_recognizers(new_org_recognizers)
            new_organism.set_connectors(new_org_connectors)
            new_organism.set_row_to_pssm()

            #if "isTracked" in organism.keys():  # !!! organism tracking needs to be reimplemented with chain-organisms
            #    new_organism.set_is_tracked(organism["isTracked"])

            organism_list.append(new_organism)

        return organism_list

    def import_connector(self, connector: dict) -> ConnectorObject:
        """Import Connector from JSON object

        Args:
            connector: connector in dictionary format

        Returns:
            Connector object from given connector dictionary
        """
        new_connector = ConnectorObject(
            connector["mu"], connector["sigma"], self.conf_con
        )

        return new_connector

    def import_pssm(self, pssm: dict) -> PssmObject:
        """Import PSSM from JSON object

        Args:
            pssm: pssm recognizer in dictionary format

        Returns:
            PSSM Object from given  pssm dictionary

        """
        return PssmObject(np.array(pssm["pwm"]), self.conf_pssm)

    def export_organisms(self, a_organisms: list, filename: str) -> None:
        """Export a list of organisms to JSON format

        Args:
            a_organisms: list of organisms to export
            filename: name of the file to export all the organisms
        """
        
        list_json_organisms = []
        for o_organism in a_organisms:
            organism = []
            for i in range(o_organism.count_recognizers() - 1):
                organism.append(self.export_pssm(o_organism.recognizers[i]))
                organism.append(self.export_connector(o_organism.connectors[i]))
            organism.append(self.export_pssm(o_organism.recognizers[-1]))
            list_json_organisms.append(organism)
        
        with open(filename, "w+") as json_file:
            json.dump(list_json_organisms, json_file, indent=2)

    def export_connector(self, o_connector: ConnectorObject) -> dict:
        """Export connector object

        Args:
            o_connector: Connector to export

        Returns:
            Connector in dictionary format
        """
        connector = {}
        connector["objectType"] = "connector"
        connector["mu"] = o_connector._mu
        connector["sigma"] = o_connector._sigma

        return connector

    def export_pssm(self, o_pssm: PssmObject) -> dict:
        """Export PSSM object

        Args:
            o_pssm: PSSM object to export

        Returns:
            pssm in dictionary format

        """
        pssm = {}
        pssm["objectType"] = "pssm"
        pssm["pwm"] = o_pssm.pwm.tolist()
        return pssm
    
    
    def get_children(self, par1, par2, reference_dna_seq, pos_dna_sample):
        '''
        Implements the recombination operator.
        Fisrt, an abstract representation of the aligned parents is produced.
        Then, the symbols of these representations are swapped, generating the
        representations of the children. In this way we define which nodes will
        go in each child.
        Finally, the actual children organism objects are compiled accordingly.
        
        Parameters
        ----------
        par1 : OrganismObject
            First parent.
        par2 : OrganismObject
            Second parent.
        reference_dna_seq : string
            The DNA sequence on which the parents are placed, so that they
            become 'aligned' one against the other.
        pos_dna_sample : list
            A random subset of the positive set. It's used in case it's
            necessary to make some synthetic connectors (for the children). The
            average distance and the standard deviation will be estimated using
            this sample.

        Returns
        -------
        child1 : OrganismObject
            First child.
        child2 : OrganismObject
            Second child.

        '''
        
        # Initialize child 1 as an empty organism
        child1 = OrganismObject(self.get_id(), self.conf_org, self.conf_pssm["MAX_COLUMNS"])
        
        # Initialize child 2 as an empty organism
        child2 = OrganismObject(self.get_id(), self.conf_org, self.conf_pssm["MAX_COLUMNS"])
        
        # Place the parents on all the sequences in the sample of the positive set
        par1_placements, par2_placements = self.store_parents_placemnts(par1, par2, pos_dna_sample)
        
        # Representation of the two parents aligned
        parents_repres = self.get_aligned_parents_repr(par1, par2, reference_dna_seq)
        
        # Table storing info about what connectors are available to cover the possible spans
        connectors_table = self.annotate_available_connectors(parents_repres)
        
        # Representation of the two recombined children aligned
        children_repres = self.get_aligned_children_repr(parents_repres, child1._id, child2._id)
        
        # Assemble child 1
        # Write the assembly instructions
        child1.set_assembly_instructions(children_repres.organism1, connectors_table, par1._id, par2._id)
        # Now compile child 1
        self.compile_recognizers(child1, par1, par2)
        self.compile_connectors(child1, par1, par2, parents_repres,
                                par1_placements, par2_placements)
        
        # Assemble child 2
        # Write the assembly instructions
        child2.set_assembly_instructions(children_repres.organism2, connectors_table, par1._id, par2._id)
        # Now compile child 2
        self.compile_recognizers(child2, par1, par2)
        self.compile_connectors(child2, par1, par2, parents_repres,
                                par1_placements, par2_placements)
        
        return child1, child2
    
    def store_parents_placemnts(self, parent1, parent2, dna_seq_set):
        '''
        Places each parent on each DNA sequence in the given list of sequences.
        Returns all the placements in a list, for each organism.
        '''
        p1_placements = []
        p2_placements = []
        
        for dna_seq in dna_seq_set:
            p1_placements.append(parent1.get_placement(dna_seq, traceback=True))
            p2_placements.append(parent2.get_placement(dna_seq, traceback=True))
        
        return p1_placements, p2_placements
    
    def get_aligned_parents_repr(self, parent1, parent2, dna_seq):
        '''
        Places both the parents on the given DNA sequence, in order to 'align'
        them, one against the other. An abstract representation of the two
        aligned parents is returned as lists of symbols.
        
        EXAMPLE:
        This scheme
        
            p1_0    p1_1    -
            -       p2_0    p2_1
        
        says that recognizer 1 of parent1 ('p1') overlaps with recognizer 0 of
        parent2 ('p2'). Instead, recognizer 0 of parent 1 is unpaired, placing
        to the left of where parent2 is placed. Recognizer 1 of parent2 is also
        unpaired, placing to the right of where parent1 is placed.
        This scheme would be returned as a couple of lists:
        
            (
                ['p1_0', 'p1_1', '-'],
                ['-', 'p2_0', 'p2_1']
            )
        
        '''
        # These dictionaries say which recognizer of an organism is occupying a
        # certain DNA position
        pos_to_recog_dict1 = self.get_pos_to_recog_idx_dict(parent1, dna_seq, 'p1')
        pos_to_recog_dict2 = self.get_pos_to_recog_idx_dict(parent2, dna_seq, 'p2')
        
        # !!!
        # Initialize the representation object of the aligned parents
        parents_repres = AlignedOrganismsRepresentation(parent1._id, parent2._id)
        
        p1_repres = []
        p2_repres = []
        
        # All the encountered pairs (each pair is made of one element from parent1,
        # and the other from parent2) are stored in this set
        pairs = set([])
        
        for i in range(len(dna_seq)):
            p1, p2 = '-', '-'
            
            if i in pos_to_recog_dict1.keys():
                p1 = pos_to_recog_dict1[i]
            
            if i in pos_to_recog_dict2.keys():
                p2 = pos_to_recog_dict2[i]
            
            pair = (p1, p2)
            # ignore DNA regions where there aren't recogs
            if pair != ('-','-'):
                
                # avoid repeating the match for all the DNA positions where the
                # match occurs
                if pair not in pairs:
                    pairs.add(pair)
                    # Compile parents representations
                    p1_repres.append(p1)
                    p2_repres.append(p2)
        
        # Remove protrusions
        '''
        A 1-bp overlap between recognizers is enough for them to get 'paired'.
        This means that the overlap can be imperfect, with flanking parts of
        the recognizers being unpaired. Those will be ignored.
        
        EXAMPLE:
        If two recognizers are placed on DNA in this way
            -----AAAA-------
            -------BBBB-----
        the desired representation is
            A
            B
        and not
            AA-
            -BB
        Therefore, the two positions to the left and to the right of the
        A-B match will be called 'protrusions', and they will be removed
        '''
        matches_p1 = set([])  # recogs of parent1 that overlap with a recog
        matches_p2 = set([])  # recogs of parent1 that overlap with a recog
        
        for i in range(len(p1_repres)):
            p1_node, p2_node = p1_repres[i], p2_repres[i]
            if p1_node != '-' and p2_node != '-':
                matches_p1.add(p1_node)
                matches_p2.add(p2_node)
        
        
        # If recognizer X is in matches_p1 or matches_p2 (menaing that it
        # overlaps at least once with another recognizer) all the other
        # eventual pairings of X with "-" are protrusions.
        
        # Here we store the indexes of the positions where there's a 'protrusion'
        protrusions = []        
        
        for i in range(len(p1_repres)):
            if p1_repres[i] in matches_p1:
                if p2_repres[i] == '-':
                    protrusions.append(i)
        
        for i in range(len(p2_repres)):
            if p2_repres[i] in matches_p2:
                if p1_repres[i] == '-':
                    protrusions.append(i)
        
        
        # Skip the protrusions and return the desired representations
        p1_repres = [p1_repres[i] for i in range(len(p1_repres)) if i not in protrusions]
        p2_repres = [p2_repres[i] for i in range(len(p2_repres)) if i not in protrusions]
        
        parents_repres.set_organsism1(p1_repres)
        parents_repres.set_organsism2(p2_repres)
        
        #return (p1_repres, p2_repres)
        return parents_repres
    
    def get_pos_to_recog_idx_dict(self, org, dna_seq, org_tag):
        '''
        The given organism is placed on the given DNA sequence.
        Each DNA position covered by some recognizer is mapped to a string,
        saying what recognizer is placed there. The string will contain a tag
        for the organism (org_tag argument), joint with the recog index by an
        underscore.
        
        EXAMPLE:
        This dictionary
            {112: 'p1_0', 113: 'p1_0', 114: 'p1_0', 115: 'p1_0'}
        will be used to know that position 114 is covered by recognizer 0.
        In this case, 'p1' was the org_tag value specified as input, used to
        identify an organism.
        
        Parameters
        ----------
        org : OrganismObject
        dna_seq : string
        org_tag : string

        Returns
        -------
        pos_to_recog_dict : dictionary

        '''
        org_placement = org.get_placement(dna_seq, traceback=True)        
        recog_positions = org_placement.recognizers_positions
        
        pos_to_recog_dict = {}
        
        # for each recognizer
        for i in range(len(recog_positions)):
            # start and stop DNA positions of recognizer i
            start, stop = recog_positions[i]
            
            # DNA positions occupied by this recognizer
            for pos in range(start, stop):
                pos_to_recog_dict[pos] = org_tag + '_' + str(i)  # i is the recog idx
        
        return pos_to_recog_dict
    
    def annotate_available_connectors(self, parents_repres):
        '''
        The representations of the aligned parents are lists of symbols.
        For each possible couple of positions in the representations, this
        function annotates whether the parents have a connector that connects
        them.
        
        EXAMPLE:
        In this representations
        
            p1_0    p1_1    -       p1_2
            -       p2_0    p2_1    -   
        
        index 0 is liked to index 1 by the first connector of p1 (parent1): the
        connector that connects recognizer p1_0 with recognizer p1_1.
        
        Index 1 is liked to index 3 by the second connector of p1: the
        connector that connects recognizer p1_1 with recognizer p1_2.
        
        Index 2 is liked to index 3 by the only connector of p2: the
        connector that connects recognizer p2_0 with recognizer p2_1.
        
        Parameters
        ----------
        parent1_repres : list
            Representation of parent1 (aligned against parent2).
        parent2_repres : list
            Representation of parent2 (aligned against parent1).

        Returns
        -------
        connectors_table : 2D list
            This table stores at row i, column j the connector(s) available to
            link index i to index j.

        '''
        
        n = len(parents_repres.organism1)
        
        # 2D list where each item is an emtpy list
        connectors_table = [[ [] for i in range(n)] for j in range(n)]
        
        # Each parent representation is coupled with a tag ('p1' or 'p2')
        parents = [(parents_repres.organism1, 'p1'),
                   (parents_repres.organism2, 'p2')]
        
        for (org_repr, org_tag) in parents:
            
            # Indexes where a recognizer of this parent is present        
            recogs_indexes = []
            for idx in range(len(org_repr)):
                if org_repr[idx] != '-':
                    recogs_indexes.append(idx)
            
            connector_idx = 0
            for i in range(len(recogs_indexes)-1):
                
                left_recog_idx = recogs_indexes[i]
                right_recog_idx = recogs_indexes[i+1]
                
                left_recog_name = org_repr[left_recog_idx]
                right_recog_name = org_repr[right_recog_idx]
                
                if left_recog_name != right_recog_name:                
                    connector_name = org_tag + '_' + str(connector_idx)
                    connector_idx += 1
                    connectors_table[left_recog_idx][right_recog_idx].append(connector_name)
        # Return the table storing info about available connectors
        return connectors_table
    
    def get_aligned_children_repr(self, parents_repres, child1_id, child2_id):
        '''
        This function swaps parts of the representations of the two parents, in
        order to get the representations of the two children.
        '''
        # Define the chunks of the aligned representations that will work as
        # independent units of the recombination process
        units = self.define_independent_units(parents_repres)
        
        # Initialize representation of the children as identical copies of the parents
        #c1_repr = copy.deepcopy(parent1_repres)  # child1
        #c2_repr = copy.deepcopy(parent2_repres)  # child2
        
        # Initialize representation of the children as identical copies of the parents
        children_repres = copy.deepcopy(parents_repres)
        children_repres.set_children_IDs(child1_id, child2_id)
        
        # Within each unit, perform a swap with 50% probability
        for (start, stop) in units:
            if random.random() < 0.5:
                # Perform the swapping, which means that the part from parent1 will
                # end up into child2, and the part from parent2 will end up into child1
                '''
                tmp = c1_repr[start: stop]
                c1_repr[start: stop] = c2_repr[start: stop]
                c2_repr[start: stop] = tmp
                '''
                children_repres.swap_unit(start, stop)
        
        return children_repres
    
    def define_independent_units(self, parents_repres):
        '''
        This function is used to define what chunks of the organisms'
        representation are going to work as independent units in the
        recombination process. Within each unit, the part from parent1 can be
        swapped with the part from parent2 (by get_aligned_children_repr function)
        with 50% probability.
        This function returns a list of units' spans, where each element is a
        (start, stop) tuple.
        
        EXAMPLE
        In this representations
        
            p1_0    p1_1    -       p1_2
            p2_0    p2_0    p2_1    -   
        
        p2_0 is partially overlapping with p1_0, and partially with p1_1. In
        this scenario, the first two positions of the representations work as a
        single unit. Therefore, the returned list of independent units will be
        
            [ (0, 2), (2, 3), (3, 4) ]
        
        '''
        
        org1_repr = parents_repres.organism1
        org2_repr = parents_repres.organism2
        
        # Initialize list about where each unit starts
        unit_starts = [0]
        
        for i in range(1, len(org1_repr)):
            
            # If in org1_repr at position i there is the same recognizer as the one
            # at position i-1
            if org1_repr[i] != '-' and org1_repr[i] == org1_repr[i-1]:
                # Then this is not yet the start of the next unit
                continue
        
            # If in org2_repr at position i there is the same recognizer as the one
            # at position i-1
            if org2_repr[i] != '-' and org2_repr[i] == org2_repr[i-1]:
                # Then this is not yet the start of the next unit
                continue
            
            unit_starts.append(i)  # i is the start position of a new unit
        
        # Each unit stops where the next unit starts (or when the list ends in the
        # case of the last unit)
        unit_stops = unit_starts[1:] + [len(org1_repr)]
        
        # Make a list of units. Each unit is a tuple: (start, stop)
        units = list(zip(unit_starts, unit_stops))
        return units
    
    def compile_recognizers(self, child_obj, parent1, parent2):
        '''
        It appends to the given organism (child_obj) the required recognizers
        from the two parents, in the right order, according to the
        assembly_instructions attribute of the organism.
        '''
        
        for recog_name in child_obj.assembly_instructions['recognizers']:
            parent, recog_idx = recog_name.split('_')
            
            if parent == 'p1':
                recog = parent1.recognizers[int(recog_idx)]
            elif parent == 'p2':
                recog = parent2.recognizers[int(recog_idx)]
            
            # Add recognizer to organism
            child_obj.append_recognizer(recog)
    
    def compile_connectors(self, child_obj, par1, par2, parents_repr,
                           par1_placements, par2_placements):
        '''
        It appends to the given organism (child_obj) the required connectors
        from the two parents, in the right order, according to the
        assembly_instructions attribute of the organism.
        
        When a required connector was not available in the parents,
        assembly_instructions requires to synthesize a new connector. This is
        done by calling the make_synthetic_connector method.
        '''
        for connector_name in child_obj.assembly_instructions['connectors']:
            
            # "synth" means that the connector needs to be synthesized, because
            # it was not available in any of the two parents
            if connector_name[:5] == 'synth':
                left_idx, right_idx = connector_name.split('_')[1:]
                
                # mu and sigma will be estimated for the gap between a left and a
                # right recognizers (on a small sample from the positive dataset).
                # Chose the left and right recognizers
                p1_left = parents_repr.organism1[int(left_idx)]
                p2_left = parents_repr.organism2[int(left_idx)]
                p1_right = parents_repr.organism1[int(right_idx)]
                p2_right = parents_repr.organism2[int(right_idx)]
                
                # When possible, chose them from the same parent
                if p1_left != '-' and p1_right != '-':
                    recog_L_name, recog_R_name = p1_left, p1_right
                elif p2_left != '-' and p2_right != '-':
                    recog_L_name, recog_R_name = p2_left, p2_right
                else:
                    if p1_left != '-':
                        recog_L_name, recog_R_name = p1_left, p2_right
                    else:
                        recog_L_name, recog_R_name = p2_left, p1_right
                # Make an appropriate connector
                conn = self.make_synthetic_connector(recog_L_name, recog_R_name,
                                                par1_placements, par2_placements)
            
            # Else, the connector can be grabbed from one of the parents
            else:
                parent, connector_idx = connector_name.split('_')
                
                if parent == 'p1':
                    # Re-use connector from parent 1
                    conn = par1.connectors[int(connector_idx)]
                elif parent == 'p2':
                    # Re-use connector from parent 2
                    conn = par2.connectors[int(connector_idx)]
            
            # Add connector to organism
            child_obj.append_connector(conn)
    
    def make_synthetic_connector(self, recog_left_name, recog_right_name,
                                 p1_placements, p2_placements):
        '''
        This function is used to generate an appropriate connector to link two
        recognizers of a child, when no one of the connectors of the parents
        is appropriate.

        Parameters
        ----------
        recog_left_name : string
            It identifies the recognizer to the left.
        recog_right_name : string
            It identifies the recognizer to the right.
        p1_placements : list
            List of placements for parent 1.
        p2_placements : list
            List of placements for parent 2.

        Returns
        -------
        synthetic_connector : ConnectorObject
            A new connector, whose mu is the average distance between the left
            and the right recognizers specified, observed in the provided
            placements, and whose sigma is the standard deviation of the
            observed distance in those same placements.

        '''
        # Get parent and node index that specify the left recognizer
        recog_left_parent, recog_left_idx = recog_left_name.split('_')
        recog_left_idx = int(recog_left_idx)
        # Get parent and node index that specify the right recognizer
        recog_right_parent, recog_right_idx = recog_right_name.split('_')
        recog_right_idx = int(recog_right_idx)
        
        gap_values = []
        for i in range(len(p1_placements)):
            
            # Placement of the left recognizer
            if recog_left_parent == 'p1':
                placement = p1_placements[i]
            elif recog_left_parent == 'p2':
                placement = p2_placements[i]
            L_first_bp, L_last_bp = self.get_recog_pos_on_DNA_seq(placement, recog_left_idx)
            
            # Placement of the right recognizer
            if recog_right_parent == 'p1':
                placement = p1_placements[i]
            elif recog_right_parent == 'p2':
                placement = p2_placements[i]
            R_first_bp, R_last_bp = self.get_recog_pos_on_DNA_seq(placement, recog_right_idx)
            
            # Gap between the left and the right recognizers
            distance = R_first_bp - L_last_bp
            gap = distance - 1
            gap_values.append(gap)
        
        # Estimate mu and sigma
        avg_gap = sum(gap_values)/len(gap_values)
        # Avoid negative mu values
        if avg_gap < 0:  # !!! temporarily hard-coded lower-bound
            avg_gap = 0
        stdev_gap = np.std(gap_values)
        # Avoid setting sigma to 0
        if stdev_gap < 0.1:  # !!! temporarily hard-coded lower-bound
            stdev_gap = 0.1
        
        synthetic_connector = ConnectorObject(avg_gap, stdev_gap, self.conf_con)
        return synthetic_connector
    
    def get_recog_pos_on_DNA_seq(self, org_placement, recog_idx):
        '''
        For a given placement and a given node index, it returns the first and
        last bp positions occupied by that node.

        Parameters
        ----------
        org_placement : dictionary
            The placement of an organism on a DNA sequence.
        node_idx : int
            Index of the desired node.

        Returns
        -------
        first_bp : int
            First DNA position occupied by the specified node.
        last_bp : int
            Last DNA position occupied by the specified node.

        '''
        
        start, stop = org_placement.recognizers_positions[recog_idx]
        
        first_bp = start  # First bp occupied
        last_bp = stop -1  # Last bp occupied
        
        return (first_bp, last_bp)









