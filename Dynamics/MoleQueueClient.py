# MoleQueueClient1.py
# This module handles communication with the local MoleQueue daemon
# using JSON-RPC 2.0 over a Unix domain socket.

import socket
import json
import os

class MoleQueueClient:
    """
    Client for communicating with a local MoleQueue daemon.
 
    MoleQueue uses JSON-RPC 2.0 over a Unix domain socket.
    Each request is prefixed with a 4-byte big-endian length header,
    followed by the UTF-8 encoded JSON payload.
    """

    def __init__(self, socket_path="/tmp/MoleQueue"):
        self.socket_path = socket_path
        self.socket = None
        self.request_id = 0


    # CONNECTION

    def connect(self):
        """
        Connect to the MoleQueue daemon via Unix domain socket.
        Returns True on success, False on failure.
        """
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(self.socket_path)
            self.socket.settimeout(5.0)
            print("MoleQueueClient: connected to MoleQueue via {}".format(self.socket_path))
            return True
        except FileNotFoundError:
            print("MoleQueueClient: ERROR — socket not found")
            return False
        except Exception as e:
            print("MoleQueueClient: ERROR — {}".format(e))
            return False
     
    def disconnect(self):
        """Close connection to MoleQueue daemon."""
        if self.socket:
            self.socket.close()
            self.socket = None
            print("MoleQueueClient: disconnected.")


    # JSON-RPC HELPERS

    def _next_id(self):
        """Generate a unique request ID."""
        self.request_id += 1
        return self.request_id

    def _send_request(self, method, params):
        """
        Send a JSON-RPC 2.0 request and return the parsed response.
        The message is prefixed with a 4-byte big-endian length header.
        Returns None if the request fails or the response is empty.
        """
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_id()
        }
        message = json.dumps(request).encode("utf-8")
	#Prefiks 4 bajtów = długość pakietu
        length = len(message).to_bytes(4, byteorder='big')
        try:
            self.socket.sendall(length + message)
            response_raw = self._receive_response()
            if response_raw:
                return json.loads(response_raw)
            else:
                print("MoleQueueClient: pusta odpowiedź od MoleQueue")
                return None
        except Exception as e:
            print("MoleQueueClient: ERROR sending request — {}".format(e))
            return None

    def _receive_response(self):
        """
        Read a response from the socket.
        First reads the 4-byte length header, then reads exactly that many bytes.
        Returns the decoded UTF-8 string, or None on timeout or connection loss.
        """

        self.socket.settimeout(5.0)
        try:
            raw_len = self.socket.recv(4)
            if not raw_len or len(raw_len) < 4:
                return None
            length = int.from_bytes(raw_len, byteorder='big')
            #Odczytaj dokładnie tyle bajtów
            data = b""
            while len(data) < length:
                chunk = self.socket.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
            return data.decode("utf-8")
        except socket.timeout:
            print("MoleQueueClient: timeout czekając na odpowiedź")
            return None

    # JOB SUBMISSION


    def submit_job(self, queue, program, input_files, project_name):
	"""
        Submit a job to MoleQueue.
 
        Args:
            queue (str): Name of the MoleQueue queue (e.g. "Local").
            program (str): Name of the program as configured in MoleQueue (e.g. "GROMACS").
            input_files (list): List of input file paths. The first file's directory
                                is used as the local working directory.
            project_name (str): Name of the project, used in the job description.
 
        Returns:
            int or None: The MoleQueue job ID on success, or None on failure.
        """

        params = {
            "queue": queue,
            "program": program,
            "description": "Dynamics PyMOL Plugin — {}".format(project_name),
            "localWorkingDirectory": os.path.dirname(input_files[0]) if input_files else "",
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


    # JOB STATUS

    def get_job_status(self, job_id):
	"""
        Check the status of a submitted job.
 
        Args:
            job_id (int): The MoleQueue job ID returned by submit_job().
 
        Returns:
            str or None: The job state string (e.g. "Finished", "Error"), or None on failure.
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

    # RESULT RETRIEVAL

    def retrieve_results(self, job_id, destination_path):
        """
        Ask MoleQueue to copy job results to a local destination path.
 
        Args:
            job_id (int): The MoleQueue job ID.
            destination_path (str): Local directory where results should be copied.
 
        Returns:
            bool: True on success, False on failure.
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
