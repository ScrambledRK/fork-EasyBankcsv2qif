#!/usr/bin/python
'''
TODO: fill me


based and inspired by http://code.google.com/p/xlscsv-to-qif/

Author: berhard.denner@gmail.com
Date: 16. Jan 2014
'''

from __future__ import print_function
import sys
import csv
import re
import argparse


encodingFrom = 'iso-8859-1'
encodingTo = 'utf-8'

parser = argparse.ArgumentParser(description='Convert a EasyBank or Bawak CSV to QIF format')
parser.add_argument('file', help='input file in CSV format. If file is - sdtin is used')
parser.add_argument('-o', '--output',
                    help="output file, to write the resulting QIF. If not given stdout is used")
parser.add_argument('-a', '--account', 
                    help="account name to use, if not given no account information will be in the QIF") 
parser.add_argument('-d', '--debug', action="store_true",
                    help='print debugging information to stderr, this option includes -s')
parser.add_argument('-s', '--summary', action="store_true",
                    help='print a summary to stderr')



doDebug = False

class Transaction(object):
    """ Transaction object, represents one transaction exratcted from the CSV
        file
    """
    def __init__(self):
        object.__init__(self)
        self.account = ""
        self.description = ""
        self.date = ""
        self.valutadate = ""
        self.amount = "0"
        self.currency = "EUR"
        self.id = ""
        self.type = None
        self.payee = None
        self.memo = None
        # debug types
        self.htype = ""
        self.desc1 = ""
        self.desc2 = ""

    def parseDescription(self):
        """parses the description field to get more detailed
        information"""
        r = re.match("^(.*)\W*([A-Z]{2})/([0-9]+)\W*(.*)?$", self.description)
        if r is not None:
            self.desc1 = r.group(1).strip()
            self.type = r.group(2)
            self.id = r.group(3)
            self.desc2 = r.group(4).strip()
            
            # transfer
            if (self.type == "BG" or self.type == "FE") \
               and len(self.desc2) > 0 and len(self.desc1) > 0:
                self.htype = "transfer"
                m = re.match("^(([A-Z0-9]+\W)?[A-Z]*[0-9]+)\W(\w+\W+\w+)\W*(.*)$", self.desc2)
                if m is not None:
                    self.payee = m.group(3) + " (" + m.group(1) + ")"
                    self.desc2 = m.group(1)
                    self.memo = self.desc1 + " " + m.group(4)
                    
            # not really a transfer, but use the information we have
            elif (self.type == "BG" or self.type == "MC") \
               and len(self.desc1) == 0:
                self.memo = self.desc2
                    
            elif (self.type == "BG" or self.type == "MC") \
               and len(self.desc2) == 0:
                self.memo = self.desc1
                
            # Maestro card (cash card) things
            elif self.type == "MC" \
                and len(self.desc1) > 0 and len(self.desc2) > 0:
                # withdraw with cash card
                m = re.match("^((Auszahlung)\W+\w+)\W*(.*)$", self.desc1)
                if m is not None:
                    self.htype = "withdraw"
                    self.memo = m.group(1)
                    if len(m.group(3)) > 0:
                        self.memo += " (" + m.group(3) + ")" 
                    self.memo += " " + self.desc2
                # payment with cash card
                m = re.match("^((Bezahlung)\W+\w+)\W*(.*)$", self.desc1)
                if m is not None:
                    self.htype = "payment"
                    self.memo = m.group(1)
                    if len(m.group(3)) > 0:
                        self.memo += " (" + m.group(3) + ")" 
                    self.memo += " " + self.desc2
            
            # mixture of transfer, cash card payments
            elif self.type == "VD":
                # if we have a value for desc1 but not for desc2
                # it may be a cash card payment
                if len(self.desc1) > 0 and len(self.desc2) == 0:
                    self.htype = "payment"
                    self.memo = self.desc1
                    
                # if we have values for both desc fields it may be a transfer
                elif len(self.desc1) > 0 and len(self.desc2) > 0:
                    self.htype = "transfer"
                    self.memo = self.desc1
                    m = re.match("^(([A-Z0-9]+\W)?[A-Z]*[0-9]+)?\W*(\w+\W+\w+)\W*(.*)$", self.desc2)
                    if m is not None:
                        self.payee = m.group(3)
                        if m.group(1) is not None:
                            self.payee += " (" + m.group(1) + ")"
                        
                        self.memo += " " + m.group(4)
                        
            # seems to be an cash card payment, however, I don't have enough
            # infos about it
            #elif self.type == "OG":
            else:
                # use what we have
                self.memo = self.desc1 + " " + self.desc2
        
        # if we got an unkown description field, use it as memo
        else:
            self.memo = self.description    
                        
        if self.htype == "":
            self.htype = 'unknown'

            
    def printDebug(self):
        print('account: {},'.format(self.account),
              'date: {},'.format(self.date),
              'amount: {} {}'.format(self.amount, self.currency), 
              file=sys.stderr)

        print('desc: {}'.format(self.description),
              'type,h: {},{}'.format(self.type, self.htype),
              #'   id: {}'.format(self.id),
              '    2: {}'.format(self.desc2),
              '    1: {}'.format(self.desc1),
              'payee: {}'.format(self.payee),
              ' memo: {}'.format(self.memo),
              '-------------------------------------------',
              file=sys.stderr, sep='\n')

        
    def getQIFstr(self):
        ret = 'D{}\n'.format(self.date) + \
              'T{}\n'.format(self.amount) + \
              'M{}\n'.format(self.memo)

        if self.payee is not None:
            ret += 'P{}\n'.format(self.payee)
        info = None
        if self.htype is not None:
            info = self.htype
        elif self.type is not None:
            info = self.type
        if info is not None:
            ret += 'N{}\n'.format(info)
        ret += '^\n'
        return ret



class EasyCSV2QIFconverter:
    """create for each row of the given CSV a Transaction object
       a outputs this Transaction object to the given output file stream
    """
    def __init__(self, instream, outstream, account=None):
        self._instream = instream
        self._outstream = outstream
        self._account = account
        self._transSummary = {}

    def convert(self):
        if self._account is not None:
            print('!Account',
                  'N{}'.format(self._account),
                  'Tcash',
                  '^',
                  '!Type:Bank', 
                  sep='\n', file=self._outstream)

        rows = csv.reader(self._instream, delimiter=';')
        for l in rows:
            if len(l) < 6:
                print ('ignoring invalid line:', l, file=sys.stderr)
                continue
            t = Transaction()
            t.account = l[0].decode(encodingFrom).encode(encodingTo)
            t.description = l[1].decode(encodingFrom).encode(encodingTo) 
            t.date = l[2].decode(encodingFrom).encode(encodingTo) 
            t.valutadate = l[3].decode(encodingFrom).encode(encodingTo) 
            t.amount = l[4].decode(encodingFrom).encode(encodingTo) 
            t.currency = l[5].decode(encodingFrom).encode(encodingTo) 
            t.parseDescription()
            self._outstream.write(t.getQIFstr())
            if doDebug:
                t.printDebug()

            if t.htype in self._transSummary:
                self._transSummary[t.htype] += 1
            else:
                self._transSummary[t.htype] = 1

    
    def getSummary(self):
        ret = ""
        count = 0
        for k, v in self._transSummary.iteritems():
            ret += '  {}:\t{}\n'.format(k, v)
            count += v
        ret += 'total transcation converted: {}\n'.format(count)
        return ret

    def printSummary(self):
        print(self.getSummary(), file=sys.stderr)



if __name__ == "__main__":
    args = parser.parse_args()
    if args.debug:
        doDebug = True

    outstream = None
    instream = None

    if args.file != "-":
        try:
            instream = open(args.file, 'r')
        except IOError as detail:
            print('could not open input file:', detail, file=sys.stderr)
            sys.exit(1)

    else:
        instream = sys.stdin

    
    if args.output:
        try:
            outstream = open(args.output, 'w')
        except IOError as detail:
            print('could not open output file:', detail, file=sys.stderr)
            sys.exit(1)

    else:
        outstream = sys.stdout

    converter = EasyCSV2QIFconverter(instream, outstream, args.account)
    converter.convert()
    if args.debug or args.summary:
        converter.printSummary()

    if args.file != "-":
        instream.close()
    if args.output:
        outstream.close()


