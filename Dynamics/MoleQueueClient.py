# MoleQueueClient.py
# This module handles communication with the local MoleQueue daemon
# using JSON-RPC 2.0 over a local socket.

import socket
import json
import os

class MoleQueueClient:
    """
    Client for communicating with a local MoleQueue daemon.
    MoleQueue uses JSON-RPC 2.0 over a local TCP socket.
    """

    def __init__(self, host="localhost", port=17243):
        self.host = host
        self.port = port
        self.socket = None
        self.request_id = 0

    # ─────────────────────────────────────────────
    # CONNECTION
    # ─────────────────────────────────────────────

    def connect(self):
        """Open connection to local MoleQueue daemon."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print("MoleQueueClient: connected to MoleQueue on port {}".format(self.port))
            return True
        except ConnectionRefusedError:
            print("MoleQueueClient: ERROR — could not connect to MoleQueue.")
            print("Make sure MoleQueue is installed and running.")
            return False

    def disconnect(self):
        """Close connection to MoleQueue daemon."""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("MoleQueueClient: disconnected.")

    # ─────────────────────────────────────────────
    # JSON-RPC HELPERS
    # ─────────────────────────────────────────────

    def _next_id(self):
        """Generate a unique request ID."""
        self.request_id += 1
        return self.request_id

    def _send_request(self, method, params):
        """
        Send a JSON-RPC 2.0 request and return the response.
        JSON-RPC format:
        {
            "jsonrpc": "2.0",
            "method": "methodName",
            "params": { ... },
            "id": 1
        }
        """
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_id()
        }
        message = json.dumps(request) + "\n"
        try:
            self.socket.sendall(message.encode("utf-8"))
            response_raw = self._receive_response()
            response = json.loads(response_raw)
            return response
        except Exception as e:
            print("MoleQueueClient: ERROR sending request — {}".format(e))
            return None

    def _receive_response(self):
        """Read response from socket until newline."""
        data = b""
        while True:
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        return data.decode("utf-8").strip()

    # ─────────────────────────────────────────────
    # JOB SUBMISSION
    # ─────────────────────────────────────────────

    def submit_job(self, queue, program, input_files, project_name):
        """
        Submit a job to MoleQueue.

        Parameters:
            queue        -- name of the PBS queue on the remote server
            program      -- program to run (e.g. "GROMACS")
            input_files  -- list of local file paths to send
            project_name -- name of the project (used as job name)

        Returns:
            job_id if successful, None if failed
        """
        params = {
            "queue": queue,
            "program": program,
            "description": "Dynamics PyMOL Plugin — {}".format(project_name),
            "inputAsPath": os.path.dirname(input_files[0]) if input_files else "",
            "inputFiles": input_files,
        }

        print("MoleQueueClient: submitting job '{}' to queue '{}'".format(project_name, queue))
        response = self._send_request("submitJob", params)

        if response and "result" in response:
            job_id = response["result"].get("moleQueueId")
            print("MoleQueueClient: job submitted, ID = {}".format(job_id))
            return job_id
        else:
            print("MoleQueueClient: ERROR — job submission failed.")
            print("Response: {}".format(response))
            return None

    # ─────────────────────────────────────────────
    # JOB STATUS
    # ─────────────────────────────────────────────

    def get_job_status(self, job_id):
        """
        Check the status of a submitted job.

        Possible statuses returned by MoleQueue:
            "Accepted", "QueuedLocal", "Submitted",
            "QueuedRemote", "RunningRemote", "Finished",
            "Error", "Canceled"

        Returns status string or None if failed.
        """
        params = {"moleQueueId": job_id}
        response = self._send_request("lookupJob", params)

        if response and "result" in response:
            status = response["result"].get("jobState")
            print("MoleQueueClient: job {} status = {}".format(job_id, status))
            return status
        else:
            print("MoleQueueClient: ERROR — could not get job status.")
            return None

    # ─────────────────────────────────────────────
    # RESULT RETRIEVAL
    # ─────────────────────────────────────────────

    def retrieve_results(self, job_id, destination_path):
        """
        Ask MoleQueue to copy results to a local destination path.

        Parameters:
            job_id           -- MoleQueue job ID
            destination_path -- local folder where results should be saved
        """
        params = {
            "moleQueueId": job_id,
            "outputDirectory": destination_path
        }
        print("MoleQueueClient: retrieving results for job {} to {}".format(job_id, destination_path))
        response = self._send_request("retrieveJobOutput", params)

        if response and "result" in response:
            print("MoleQueueClient: results retrieved successfully.")
            return True
        else:
            print("MoleQueueClient: ERROR — could not retrieve results.")
            return False