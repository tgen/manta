//
// Manta - Structural Variant and Indel Caller
// Copyright (c) 2013-2017 Illumina, Inc.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
//
//

#include "bam_record_util.hh"
#include "align_path_bam_util.hh"


bool
is_mapped_pair(
    const bam_record& bam_read)
{
    if (! bam_read.is_paired()) return false;
    if (bam_read.is_unmapped() || bam_read.is_mate_unmapped()) return false;
    return true;
}



bool
is_mapped_chrom_pair(
    const bam_record& bam_read)
{
    if (! is_mapped_pair(bam_read)) return false;
    if (bam_read.target_id() != bam_read.mate_target_id()) return false;
    return true;
}



bool
is_innie_pair(
    const bam_record& bam_read)
{
    if (! is_mapped_chrom_pair(bam_read)) return false;
    if (bam_read.is_fwd_strand() == bam_read.is_mate_fwd_strand()) return false;

    if     (bam_read.pos() < bam_read.mate_pos())
    {
        if (! bam_read.is_fwd_strand()) return false;
    }
    else if (bam_read.pos() > bam_read.mate_pos())
    {
        if (  bam_read.is_fwd_strand()) return false;
    }

    return true;
}



bool
is_possible_adapter_pair(
    const bam_record& bamRead,
    const bool isAgressive)
{
    if (! is_mapped_chrom_pair(bamRead)) return false;
    if (bamRead.is_fwd_strand() == bamRead.is_mate_fwd_strand()) return false;

    // get range of alignment before matching softclip:
    int posDiff(bamRead.mate_pos()-bamRead.pos());
    if (! bamRead.is_fwd_strand())
    {
        posDiff *= -1;
    }

    // Aggressive check: the pos difference between the reverse read and the forwarding read is [-50, 10]
    bool isCandidate((posDiff < 10) && (posDiff > -50));
    if (! isCandidate) return false;
    // The aggressive check is applied for candidate/hypothesis generation
    // to avoid large number of spurious small indels for short insert data that are derived from adapter k-mers
    else if (isAgressive) return true;

    // A less aggressive check is applied for read filtration of assembly to avoid missing any evidence reads
    // if the read (primary) contains a SA tag, keep it for assembly
    if (bamRead.isSASplit()) return false;

    using namespace ALIGNPATH;
    path_t apath;
    bam_cigar_to_apath(bamRead.raw_cigar(), bamRead.n_cigar(), apath);
    // if the read contains soft clip on the 3' end, it likely runs into adapter.
    unsigned softClipSize;
    if (bamRead.is_fwd_strand())
    {
        softClipSize = apath_soft_clip_trail_size(apath);
    }
    else
    {
        softClipSize = apath_soft_clip_lead_size(apath);
    }

    isCandidate = (softClipSize > 0);
    return (isCandidate);
}



bool
is_overlapping_pair(
    const bam_record& bamRead,
    const SimpleAlignment& matchedAlignment)
{
    if (! is_mapped_chrom_pair(bamRead)) return false;
    if (bamRead.is_fwd_strand() == bamRead.is_mate_fwd_strand()) return false;

    // we want a substantial gap between pos and mate-pos before we switch from
    // treating the read pair as an overlapping standard mate pair to a duplicate pair.
    //static const int dupDist(50);

    // get range of alignment after matching all softclip:
    if (bamRead.is_fwd_strand())
    {
        // is this likely to be a duplication read pair?:
        //if (((matchedAlignment.pos+1)-bamRead.mate_pos()) >= dupDist) return false;

        const pos_t matchedEnd(matchedAlignment.pos + apath_ref_length(matchedAlignment.path));
        return (matchedEnd >= bamRead.mate_pos());
    }
    else
    {
        // is this likely to be a duplication read pair?:
        //if ((bamRead.mate_pos()-(matchedAlignment.pos+1)) >= dupDist) return false;

        const pos_t matchedBegin(matchedAlignment.pos);
        return (matchedBegin <= bamRead.mate_pos());
    }
}



unsigned
get_avg_quality(
    const bam_record& bam_read)
{
    const unsigned len(bam_read.read_size());
    if (0 == len) return 0;

    const uint8_t* qual(bam_read.qual());
    unsigned sum(0);
    for (unsigned i(0); i<len; ++i)
    {
        sum+=qual[i];
    }
    // this does not capture the decimal remainder but well...
    return (sum/len);
}
