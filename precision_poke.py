#!/usr/bin/env python

import os
import sys
import time
import re
import subprocess
import argparse

def get_slurm_queue():
    """Returns a set of all submitted Job IDs for the current user."""
    try:
        output = subprocess.check_output("squeue -u $USER -o %i", shell=True).decode()
        return set(output.split())
    except:
        return set()

def poke_wdirs(head_node, work_dirs):
    """SSH to the head node and poke the .exitcode files."""
    paths = " ".join([f"{d}/.exitcode" for d in work_dirs])
    cmd = f"ssh -n {head_node} 'stat {paths} > /dev/null 2>&1'"
    subprocess.call(cmd, shell=True)
    return

def check_log(log_path, last_log_pos):
    """Grab only the latest part of log and update position"""
    with open(log_path) as f:
        f.seek(last_log_pos)
        new_entries = f.readlines()
        new_pos = f.tell()
    return new_entries, new_pos

def check_processes(log, running):
    """Get a dict of job id: workdir for submitted jobs. Completed tasks are filtered out"""
    submit_re = re.compile(r"jobId: (\d+); workDir: (\S+)")
    complete_re = re.compile(r"jobId: (\d+);.*status: COMPLETED")

    for line in log:
        s_match = submit_re.search(line)
        if s_match:
            jid = s_match.group(1)
            wdir = s_match.group(2).rstrip(';]')
            running[jid] = wdir
            continue

        c_match = complete_re.search(line)
        if c_match:
            jid = c_match.group(1)
            running.pop(jid, None)
    return running

def initialize():
    parser = argparse.ArgumentParser(
            description="Identifies stalled nextflow processes and revives them.")
    parser.add_argument(
            "-j", required=True, help="Head process JobID")
    parser.add_argument(
            "-n", required=True, help="Node on which head process is running")
    parser.add_argument(
            "-l", required=True, help="Full path to .nextflow.log")
    args = parser.parse_args()
    return args.j, args.n, args.l

def main():
    main_job_id, main_job_node, log_path = initialize()

    last_mtime   = 0
    last_log_pos = 0
    running_jobs = {}

    while True:
        try:
            active_queue = get_slurm_queue()
            if main_job_id not in active_queue:
                print(f"Main job not active. Check {log_path}")
                sys.exit()

            current_mtime = os.path.getmtime(log_path)
            if current_mtime > last_mtime:
                new_entries, new_pos = check_log(log_path, last_log_pos)
                running_jobs = check_processes(new_entries, running_jobs)

                stalled_dirs = [wdir for jid, wdir in running_jobs.items()
                                if jid not in active_queue]

                if stalled_dirs:
                    print(f"Poking {len(stalled_dirs)} workdir(s)..")
                    poke_wdirs(main_job_node, stalled_dirs)

                last_mtime = current_mtime
                last_log_pos = new_pos
        except FileNotFoundError:
            print(f"{log_path} not found..")
            sys.exit()
    
        time.sleep(30) 

if __name__ == "__main__":
    main()

