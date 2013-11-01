#
# Manta
# Copyright (c) 2013 Illumina, Inc.
#
# This software is provided under the terms and conditions of the
# Illumina Open Source Software License 1.
#
# You should have received a copy of the Illumina Open Source
# Software License 1 along with this program. If not, see
# <https://github.com/sequencing/licenses/>
#

"""
This provides a function to auto-generate a workflow run script.
"""

import os, sys

from configureUtil import dumpIniSections



def makeRunScript(scriptFile,workflowModulePath,workflowClassName,primaryIniSection,iniSections, pythonBin=None) :
    """
    This function generates the python workflow runscript

    The auto-generated python script presents the user with options to
    run and/or continue their workflow, and reads all workflow
    configuration info from an ini file.

    scriptFile -- file name of the runscript to create
    workflowModulePath -- the python module containing the workflow class
    workflowClassName -- the workflow class name
    primaryIniSection -- the section used to create the primary workflow parameter object
    iniSections -- a hash or hashes representing all configuration info
    @param pythonBin: optionally specify a custom python interpreter for the script she-bang
    """
    import inspect

    assert os.path.isdir(os.path.dirname(scriptFile))
    assert os.path.isfile(workflowModulePath)

    workflowModulePath=os.path.abspath(workflowModulePath)
    workflowModuleDir=os.path.dirname(workflowModulePath)
    workflowModuleName=os.path.basename(workflowModulePath)
    pyExt=".py"
    if workflowModuleName.endswith(pyExt) :
        workflowModuleName=workflowModuleName[:-len(pyExt)]

    # dump inisections to a file
    iniFile=scriptFile+".ini"
    dumpIniSections(iniFile,iniSections)

    sfp=open(scriptFile,"w")

    if pythonBin is None :
        pythonBin="/usr/bin/env python"

    sfp.write(runScript1 % (pythonBin, " ".join(sys.argv),workflowModuleDir,workflowModuleName,workflowClassName))

    sfp.write(inspect.getsource(get_run_options))
    sfp.write('\n')
    sfp.write(inspect.getsource(main))
    sfp.write('\n')
    sfp.write('main("%s","%s",%s)\n' % (iniFile,primaryIniSection,workflowClassName))
    sfp.write('\n')
    sfp.close()
    os.chmod(scriptFile,0755)



runScript1="""#!%s
# Workflow run script auto-generated by command: '%s'
#

import os, sys

scriptDir=os.path.abspath(os.path.dirname(__file__))
sys.path.append('%s')

from %s import %s

"""


# This code will be reflected in the auto-generated runscript,
# but will not be called in this module:
def get_run_options(workflowClassName) :

    from optparse import OptionGroup

    from configureUtil import EpilogOptionParser
    from estimateHardware import EstException, getNodeHyperthreadCoreCount, getNodeMemMb

    version="@MANTA_FULL_VERSION@"

    sgeDefaultCores=workflowClassName.runModeDefaultCores('sge')

    epilog="""Note this script can be re-run to continue the workflow run in case of interruption.
Also note that dryRun option has limited utility when task definition depends on upstream task
results -- in this case the dry run will not cover the full 'live' run task set."""

    parser = EpilogOptionParser(description="Version: %s" % (version), epilog=epilog, version=version)


    parser.add_option("-m", "--mode", type="string",dest="mode",
                      help="select run mode (local|sge)")
    parser.add_option("-q", "--queue", type="string",dest="queue",
                      help="specify sge queue name")
    parser.add_option("-j", "--jobs", type="string",dest="jobs",
                  help="number of jobs, must be an integer or 'unlimited' (default: Estimate total cores on this node for local mode, %s for sge mode)" % (sgeDefaultCores))
    parser.add_option("-g","--memGb", type="string",dest="memGb",
                  help="gigabytes of memory available to run workflow -- only meaningful in local mode, must be an integer  (default: Estimate the total memory for this node for local mode, 'unlimited' for sge mode)")
    parser.add_option("-e","--mailTo", type="string",dest="mailTo",action="append",
	              help="send email notification of job completion status to this address (may be provided multiple times for more than one email address)")
    parser.add_option("-d","--dryRun", dest="isDryRun",action="store_true",default=False,
                      help="dryRun workflow code without actually running command-tasks")

    debug_group = OptionGroup(parser,"development debug options")
    debug_group.add_option("--rescore", dest="isRescore",action="store_true",default=False,
                          help="Reset task list to re-run hypothesis generation and scoring without resetting graph generation.")

    parser.add_option_group(debug_group)

    (options,args) = parser.parse_args()

    if len(args) :
        parser.print_help()
        sys.exit(2)

    if options.mode is None :
        parser.print_help()
        sys.exit(2)
    elif options.mode not in ["local","sge"] :
        parser.error("Invalid mode. Available modes are: local, sge")

    if options.jobs is None :
        if options.mode == "sge" :
            options.jobs = sgeDefaultCores
        else :
            try :
                options.jobs = getNodeHyperthreadCoreCount()
            except EstException:
                parser.error("Failed to estimate cores on this node. Please provide job count argument (-j).")
    if options.jobs != "unlimited" :
        options.jobs=int(options.jobs)
        if options.jobs <= 0 :
            parser.error("Jobs must be 'unlimited' or an integer greater than 1")

    # note that the user sees gigs, but we set megs
    if options.memGb is None :
        if options.mode == "sge" :
            options.memMb = "unlimited"
        else :
            try :
                options.memMb = getNodeMemMb()
            except EstException:
                parser.error("Failed to estimate available memory on this node. Please provide available gigabyte argument (-g).")
    elif options.memGb != "unlimited" :
        options.memGb=int(options.memGb)
        if options.memGb <= 0 :
            parser.error("memGb must be 'unlimited' or an integer greater than 1")
        options.memMb = 1024*options.memGb
    else :
        options.memMb = options.memGb

    options.schedulerArgList=[]
    if options.queue is not None :
        options.schedulerArgList=["-q",options.queue]

    options.resetTasks=[]
    if options.isRescore :
        options.resetTasks.append("makeHyGenDir")

    return options



# This code will be reflected in the auto-generated runscript,
# but will not be called in this module:
def main(iniFile, primaryIniSection, workflowClassName) :

    from configureUtil import argToBool, getIniSectionsWithPrimaryOptions

    runOptions=get_run_options(workflowClassName)
    flowOptions,iniSections=getIniSectionsWithPrimaryOptions(iniFile,primaryIniSection)

    # TODO: we need a more scalable system to deal with non-string options, for now there are individually corrected:
    flowOptions.isExome=argToBool(flowOptions.isExome)
    flowOptions.isRNA=argToBool(flowOptions.isRNA)
    flowOptions.useExistingAlignStats=argToBool(flowOptions.useExistingAlignStats)
    flowOptions.useExistingChromDepths=argToBool(flowOptions.useExistingChromDepths)

    # new logs and marker files to assist automated workflow monitoring:
    warningpath=os.path.join(flowOptions.runDir,"manta.warning.log.txt")
    errorpath=os.path.join(flowOptions.runDir,"manta.error.log.txt")
    exitpath=os.path.join(flowOptions.runDir,"manta.workflow.exitcode.txt")

    # the exit path should only exist once the workflow completes:
    if os.path.exists(exitpath) :
        if not os.path.isfile(exitpath) :
            raise Exception("Unexpected filesystem item: '%s'" % (exitpath))
        os.unlink(exitpath)

    wflow = workflowClassName(flowOptions,iniSections)

    retval=1
    try:
        retval=wflow.run(mode=runOptions.mode,
                         nCores=runOptions.jobs,
                         memMb=runOptions.memMb,
                         dataDirRoot=flowOptions.workDir,
                         mailTo=runOptions.mailTo,
                         isContinue="Auto",
                         isForceContinue=True,
                         isDryRun=runOptions.isDryRun,
                         schedulerArgList=runOptions.schedulerArgList,
                         resetTasks=runOptions.resetTasks,
                         successMsg=wflow.getSuccessMessage(),
                         warningLogFile=warningpath,
                         errorLogFile=errorpath)
    finally:
        exitfp=open(exitpath,"w")
        exitfp.write("%i\n" % (retval))
        exitfp.close()

    sys.exit(retval)


