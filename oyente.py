import shlex
import subprocess
import os
import re
import sys
import global_params
import argparse
import requests
import logging

def cmd_exists(cmd):
    return subprocess.call("type " + cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0

def has_dependencies_installed():
    try:
        import z3
        import z3util
        if z3.get_version_string() != '4.4.1':
            logging.warning("You are using an untested version of z3. 4.4.1 is the officially tested version")
    except:
        logging.critical("Z3 is not available. Please install z3 from https://github.com/Z3Prover/z3.")
        return False

    if not cmd_exists("evm"):
        logging.critical("Please install evm from go-ethereum and make sure it is in the path.")
        return False
    else:
        cmd = subprocess.Popen(["evm", "--version"], stdout = subprocess.PIPE)
        cmd_out = cmd.communicate()[0].strip()
        version = re.findall(r"evm version (\d*.\d*.\d*)", cmd_out)[0]
        if version != '1.6.1':
            logging.warning("You are using evm version %s. The supported version is 1.6.1" % version)

    if not cmd_exists("solc"):
        logging.critical("solc is missing. Please install the solidity compiler and make sure solc is in the path.")
        return False
    else:
        cmd = subprocess.Popen(["solc", "--version"], stdout = subprocess.PIPE)
        cmd_out = cmd.communicate()[0].strip()
        version = re.findall(r"Version: (\d*.\d*.\d*)", cmd_out)[0]
        if version != '0.4.10':
            logging.warning("You are using solc version %s, The supported version is 0.4.10" % version)

    return True

def removeSwarmHash(evm):
	evm_without_hash = re.sub(r"a165627a7a72305820\S{64}0029$", "", evm)
	return evm_without_hash

def main():
    # TODO: Implement -o switch.

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-s", "--source", type=str, help="local source file name. Solidity by default. Use -b to process evm instead. Use stdin to read from stdin.")
    group.add_argument("-ru", "--remoteURL", type=str, help="Get contract from remote URL. Solidity by default. Use -b to process evm instead.", dest="remote_URL")

    parser.add_argument("-b", "--bytecode", help="read bytecode in source instead of solidity file.", action="store_true")

    parser.add_argument("-j", "--json", help="Redirect results to a json file.", action="store_true")
    parser.add_argument("-e", "--evm", help="Do not remove the .evm file.", action="store_true")
    parser.add_argument("-p", "--paths", help="Print path condition information.", action="store_true")
    parser.add_argument("--error", help="Enable exceptions and print output. Monsters here.", action="store_true")
    parser.add_argument("-t", "--timeout", type=int, help="Timeout for Z3.")
    parser.add_argument("-v", "--verbose", help="Verbose output, print everything.", action="store_true")
    parser.add_argument("-r", "--report", help="Create .report file.", action="store_true")
    parser.add_argument("-gb", "--globalblockchain", help="Integrate with the global ethereum blockchain", action="store_true")
    parser.add_argument("-dl", "--depthlimit", help="Limit DFS depth", action="store", dest="depth_limit", type=int)
    parser.add_argument("-gl", "--gaslimit", help="Limit Gas", action="store", dest="gas_limit", type=int)
    parser.add_argument("-st", "--state", help="Get input state from state.json", action="store_true")
    parser.add_argument("-ll", "--looplimit", help="Limit a number of loop", action="store", dest="loop_limit", type=int)
    parser.add_argument("-w", "--web", help="Run Oyente for web service", action="store_true")

    args = parser.parse_args()

    if args.timeout:
        global_params.TIMEOUT = args.timeout

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    global_params.PRINT_PATHS = 1 if args.paths else 0
    global_params.REPORT_MODE = 1 if args.report else 0
    global_params.IGNORE_EXCEPTIONS = 1 if args.error else 0
    global_params.USE_GLOBAL_BLOCKCHAIN = 1 if args.globalblockchain else 0
    global_params.INPUT_STATE = 1 if args.state else 0
    global_params.WEB = 1 if args.web else 0

    if args.depth_limit:
        global_params.DEPTH_LIMIT = args.depth_limit
    if args.gas_limit:
        global_params.GAS_LIMIT = args.gas_limit
    if args.loop_limit:
        global_params.LOOP_LIMIT = args.loop_limit

    if not has_dependencies_installed():
        return

    if args.remote_URL:
        r = requests.get(args.remote_URL)
        code = r.text
        filename = "remote_contract.evm" if args.bytecode else "remote_contract.sol"
        args.source = filename
        with open(filename, 'w') as f:
            f.write(code)

    if args.bytecode:
        disasm_out = ""
        processed_evm_file = args.source + '.1'
        try:
            with open(args.source) as f:
                evm = f.read()

            with open(processed_evm_file, 'w') as f:
                f.write(removeSwarmHash(evm))

            disasm_p = subprocess.Popen(["evm", "disasm", processed_evm_file], stdout=subprocess.PIPE)
            disasm_out = disasm_p.communicate()[0]

        except:
            logging.critical("Disassembly failed.")
            exit()

        # Run symExec

        with open(args.source+'.disasm', 'w') as of:
            of.write(disasm_out)


        # TODO: Do this as an import and run, instead of shell call and hacky fix

        cmd = os.system('python symExec.py %s.disasm %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %s' % \
            (args.source, global_params.IGNORE_EXCEPTIONS, global_params.REPORT_MODE, global_params.PRINT_MODE, \
            global_params.DATA_FLOW, global_params.CHECK_CONCURRENCY_FP, global_params.TIMEOUT, \
            global_params.UNIT_TEST, global_params.GLOBAL_TIMEOUT, global_params.PRINT_PATHS, global_params.USE_GLOBAL_BLOCKCHAIN, \
            global_params.DEPTH_LIMIT, global_params.GAS_LIMIT, global_params.INPUT_STATE, global_params.LOOP_LIMIT, \
            global_params.WEB, args.source+".json" if args.json else ""))

        os.system('rm %s.disasm' % (args.source))
        os.system('rm %s' % (processed_evm_file))

        if global_params.UNIT_TEST == 2 or global_params.UNIT_TEST == 3:
            exit_code = os.WEXITSTATUS(cmd)
            if exit_code != 0: exit(exit_code)
        return

    # Compile first

    solc_cmd = "solc --optimize --bin-runtime %s"

    FNULL = open(os.devnull, 'w')

    solc_p = subprocess.Popen(shlex.split(solc_cmd % args.source), stdout = subprocess.PIPE, stderr=FNULL)
    solc_out = solc_p.communicate()

    binary_regex = r"\n======= (.*?) =======\nBinary of the runtime part: \n(.*?)\n"
    matches = re.findall(binary_regex, solc_out[0])

    if len(matches) == 0:
        logging.critical("Solidity compilation failed")
        exit()

    for (cname, bin_str) in matches:
        logging.info("Contract %s:" % cname)

        with open(cname+'.evm', 'w') as of:
            of.write(removeSwarmHash(bin_str))


        disasm_out = ""
        try:
            disasm_p = subprocess.Popen(["evm", "disasm", cname+'.evm'], stdout=subprocess.PIPE)
            disasm_out = disasm_p.communicate()[0]
        except:
            logging.critical("Disassembly failed.")
            exit()

        # Run symExec

        with open(cname+'.evm.disasm', 'w') as of:
            of.write(disasm_out)


        # TODO: Do this as an import and run, instead of shell call and hacky fix
        filepath = os.path.join(os.path.dirname(__file__), 'symExec.py')
        os.system('python %s %s.evm.disasm %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %s' % \
            (filepath, cname, global_params.IGNORE_EXCEPTIONS, global_params.REPORT_MODE, global_params.PRINT_MODE, \
            global_params.DATA_FLOW, global_params.CHECK_CONCURRENCY_FP, global_params.TIMEOUT, \
            global_params.UNIT_TEST, global_params.GLOBAL_TIMEOUT, global_params.PRINT_PATHS, global_params.USE_GLOBAL_BLOCKCHAIN, \
            global_params.DEPTH_LIMIT, global_params.GAS_LIMIT, global_params.INPUT_STATE, global_params.LOOP_LIMIT, \
            global_params.WEB, cname+".json" if args.json else ""))

        if args.evm:
            with open(cname+'.evm','w') as of:
                of.write(bin_str)

        os.system('rm %s.evm.disasm' % (cname))

if __name__ == '__main__':
    main()
