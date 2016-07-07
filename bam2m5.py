#!/usr/bin/env python3
"""Convert bam file to pacbio m5 format, sam MD tag is need.
Usage: python <script> <in.bam> <ref.fa> <score_scheme> <out.m5>
score_scheme: match,mismatch,gap_open,gap_extend, eg 1,-2,-1,-1"""
from __future__ import print_function
nargs = 4
from cigar import CIGAR, cigartuple
from BioUtil import samFile, xzopen, cachedFasta
import MD
import warnings
from itertools import takewhile

class mapScore:
    def __init__(self, mismatch, gap_open, gap_extend, match = 1):
        self.match = match
        self.mismatch = mismatch
        self.gap_open = gap_open
        self.gap_extend = gap_extend

    def score(self, cigar_len, cigar_count):
        score = 0
        score += self.match * cigar_len[CIGAR.EQUAL]
        score += self.mismatch * cigar_len[CIGAR.DIFF]
        score += self.gap_open * (cigar_count[CIGAR.INS] + cigar_count[CIGAR.DEL]) 
        score += self.gap_extend * (cigar_len[CIGAR.INS] + cigar_len[CIGAR.DEL])
        return int(score)

def main(inbam, fasta_file, score, out_file):
    fa = cachedFasta(fasta_file)
    with samFile(inbam, 'r') as sam, xzopen(out_file,'w') as out:
        ref_lengths = dict(zip(sam.references, sam.lengths))
        match, mismatch, gap_open, gap_extend = map(float, score.split(','))
        score_scheme = mapScore(mismatch, gap_open, gap_extend, match)
        for rec in sam:
            print(*bam2m5(rec, fa, ref_lengths, score_scheme), file=out)
    fa.close()

# m5 fileds
# qName qLength qStart qEnd qStrand tName tLength tStart tEnd tStrand score numMatch numMismatch numIns numDel mapQV qAlignedSeq matchPattern tAlignedSeq
def bam2m5(rec, fa, ref_lengths, score_scheme):
    if rec.is_unmapped:
        return None
    if not rec.has_tag('MD'):
        raise ValueError("MD tag not found: %s -> %s" 
                %(rec.query_name, req.reference_name) )
    if rec.query_sequence is None :
        warnings.warn("%s -> %s is not parsed due to no query sequece" 
                %(rec.query_name, req.reference_name) )
        return None
    md = MD.parse_tag(rec.get_tag('MD'))
    cigar = cigartuple(rec.cigartuples)
    qseq = rec.query_sequence[cigar.query_start:cigar.query_end]
    # this function may contain some bugs, read direct from fa file instead
    # rseq = rec.get_reference_sequence() 
    rseq = fa[rec.reference_name][rec.reference_start:rec.reference_end]

    pos = 0
    for op, length in cigar:
        if op in (CIGAR.EQUAL, CIGAR.DIFF, CIGAR.MATCH):
            pos += length
        elif op == CIGAR.INS:
            rseq = insert(rseq, pos, '-'*length)
            pos += length
        elif  op == CIGAR.DEL:
            qseq = insert(qseq, pos, '-'*length)
            pos += length
        elif op in (CIGAR.SOFT_CLIP, CIGAR.HARD_CLIP):
            continue
        else:
            warnings.warn("%s %s %s" %
                    (rec.query_name, CIGAR.get_name(op)))
    if (len(qseq) != len(rseq)):
        warnings.warn("sequence length not match, maybe error: %s -> %s"
                % (rec.query_name, rec.reference_name))

    if rec.is_reverse:
        qseq = reverse_complement(qseq)
        rseq = reverse_complement(rseq)
    mp = "".join('|' if q == r else '*' for q, r in zip(qseq, rseq))

    cigar_len, cigar_count = rec.get_cigar_stats()
    if cigar_len[CIGAR.EQUAL] == 0 and cigar_len[CIGAR.MATCH] > 0:
        cigar_len[CIGAR.DIFF] = sum(x.length for x in md if x.type is MD.DIFF)
        cigar_len[CIGAR.EQUAL] = cigar_len[CIGAR.MATCH] - cigar_len[CIGAR.DIFF]

    qstart = rec.query_alignment_start + cigar.left_hard_clip
    qend = rec.query_alignment_end + cigar.left_hard_clip
    qlen = rec.query_length + cigar_len[CIGAR.HARD_CLIP]
    if rec.is_reverse:
        qstart, qend = qlen - qend, qlen - qstart

    # qName qLength qStart qEnd qStrand tName tLength tStart tEnd tStrand score numMatch numMismatch numIns numDel mapQV qAlignedSeq matchPattern tAlignedSeq
    return (rec.query_name, qlen, qstart, qend, '+', '', # add a space to match m5 formating
            rec.reference_name, ref_lengths[rec.reference_name],
            rec.reference_start, rec.reference_end,
            '-' if rec.is_reverse else '+',
            score_scheme.score(cigar_len, cigar_count),
            *(cigar_len[op] for op in (CIGAR.EQUAL, CIGAR.DIFF, CIGAR.INS, CIGAR.DEL)), 
            # cigar_len[CIGAR.EQUAL], cigar_len[CIGAR.DIFF],
            # cigar_len[CIGAR.INS], cigar_len[CIGAR.DEL],
            rec.mapping_quality,
            qseq, mp, rseq,
            )

complement = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A'}
def reverse_complement(seq):
    return "".join(complement.get(base, base) for base in reversed(seq) )

def insert(string, pos, seq):
    return string[:pos] + seq + string[pos:]

if __name__ == '__main__':
    import sys
    if len(sys.argv) - 1 != nargs:
        sys.exit(__doc__)
    main(*sys.argv[1:])




        
