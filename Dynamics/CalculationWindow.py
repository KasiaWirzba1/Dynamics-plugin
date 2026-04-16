import pymol_plugin_dynamics
import queue as Queue
from tkinter import *
from tkinter.ttk import Progressbar, Scrollbar
import _thread as thread
import time
from tkinter import messagebox as tkMessageBox

# ─── MoleQueue integration ───────────────────────────────────────────────────
try:
    from MoleQueueClient import MoleQueueClient
    MOLEQUEUE_AVAILABLE = True
except ImportError:
    MOLEQUEUE_AVAILABLE = False
# ─────────────────────────────────────────────────────────────────────────────


class CalculationWindow:
    tasks_to_do = 0
    bar_var = ""
    bar_widget = ""
    start_button = ""
    start_remote_button = ""
    stop_button = ""
    log_button = ""

    def __init__(self):
        self.queue_status = Queue.Queue()
        self.queue_percent = Queue.Queue()

    # ─────────────────────────────────────────────
    # WINDOW CREATION
    # ─────────────────────────────────────────────

    def check_window(self, master, g_parent, s_params, status):
        project_name = s_params.project_name
        if project_name != "nothing":
            master.destroy()
            root = Toplevel(g_parent)
            self.window(root, s_params, status, g_parent)
        elif project_name == "nothing":
            pymol_plugin_dynamics.no_molecule_warning()

    def window(self, root, s_params, status, parent):
        self.root = root
        self.parent = parent
        frame1 = Frame(root)
        frame1.pack(side=TOP)
        frame2 = Frame(root)
        frame2.pack(side=TOP)

        self.bar_var = StringVar(root)
        self.bar_var.set("Ready to start")

        w5 = Label(frame1, textvariable=self.bar_var)
        w5.pack(side=TOP)
        self.bar_widget = Progressbar(frame1)
        self.bar_widget.pack(side=TOP)

        exit_button = Button(frame2, text="EXIT", command=root.destroy)
        exit_button.pack(side=LEFT)

        save_button = Button(frame2, text="SAVE",
                             command=lambda: pymol_plugin_dynamics.select_file_save(s_params, 1))
        save_button.pack(side=LEFT)

        stop_button = Button(frame2, text="STOP",
                             command=lambda: self.start_counting(0, s_params))
        stop_button.pack(side=LEFT)
        stop = s_params.stop
        if stop:
            stop_button.configure(state=DISABLED)
        self.stop_button = stop_button

        # ── START LOCAL ──────────────────────────────────────────────────────
        start_button = Button(frame2, text="START LOCAL",
                              command=lambda: self.start_counting(1, s_params))
        start_button.pack(side=LEFT)
        if stop == 0:
            start_button.configure(state=DISABLED)
        self.start_button = start_button

        # ── START REMOTE (MoleQueue) ─────────────────────────────────────────
        start_remote_button = Button(
            frame2,
            text="START REMOTE",
            command=lambda: self.start_counting_remote(s_params),
            bg="#4A90D9",
            fg="white",
            activebackground="#357ABD",
            activeforeground="white"
        )
        start_remote_button.pack(side=LEFT)
        if stop == 0:
            start_remote_button.configure(state=DISABLED)
        if not MOLEQUEUE_AVAILABLE:
            start_remote_button.configure(state=DISABLED)
        self.start_remote_button = start_remote_button

        log_button = Button(frame2, text="LOG",
                            command=pymol_plugin_dynamics.log_window(s_params))
        log_button.pack(side=LEFT)
        log_button.configure(state=DISABLED)
        self.log_button = log_button

        # Updating status bar
        tasks_nr = 0.0
        for task in s_params.progress.to_do:
            tasks_nr = tasks_nr + task
        self.tasks_to_do = tasks_nr
        self.start_counting(1, s_params)

        thread.start_new_thread(self.bar_update, (s_params, status))
        self.bar_display(root, parent, s_params)

    # ─────────────────────────────────────────────
    # LOCAL EXECUTION
    # ─────────────────────────────────────────────

    def start_counting(self, value, s_params):
        """Start or stop a LOCAL GROMACS calculation."""
        if value == 1:
            stop = 0
            thread.start_new_thread(pymol_plugin_dynamics.dynamics, (s_params,))
            self.stop_button.configure(state=ACTIVE)
            self.start_button.configure(state=DISABLED)
            self.start_remote_button.configure(state=DISABLED)
            self.log_button.configure(state=DISABLED)
        elif value == 0:
            stop = 1
            self.stop_button.configure(state=DISABLED)
            self.start_button.configure(state=ACTIVE)
            if MOLEQUEUE_AVAILABLE:
                self.start_remote_button.configure(state=ACTIVE)
            self.log_button.configure(state=ACTIVE)

    # ─────────────────────────────────────────────
    # REMOTE EXECUTION via MoleQueue
    # ─────────────────────────────────────────────

    def start_counting_remote(self, s_params):
        """Submit a job to MoleQueue and monitor its status."""
        self.stop_button.configure(state=ACTIVE)
        self.start_button.configure(state=DISABLED)
        self.start_remote_button.configure(state=DISABLED)
        self.log_button.configure(state=DISABLED)
        self.bar_var.set("Connecting to MoleQueue...")

        thread.start_new_thread(self._remote_worker, (s_params,))

    def _remote_worker(self, s_params):
        """
        Background thread:
        1. Connects to the local MoleQueue daemon.
        2. Submits the job.
        3. Polls for status every 5 seconds.
        4. Puts the final status into queue_status so bar_display can react.
        """
        client = MoleQueueClient()

        if not client.connect():
            self.bar_var.set("MoleQueue: connection failed!")
            tkMessageBox.showerror(
                "MoleQueue Error",
                "Cannot connect to MoleQueue daemon.\n"
                "Make sure MoleQueue is running."
            )
            self._remote_reset_buttons()
            return

        # Collect input files produced by Dynamics plugin
        input_files = self._collect_input_files(s_params)

        job_id = client.submit_job(
            queue="Local",
            program="GROMACS",
            input_files=input_files,
            project_name=s_params.project_name
        )

        if not job_id:
            self.bar_var.set("MoleQueue: job submission failed!")
            tkMessageBox.showerror(
                "MoleQueue Error",
                "Job could not be submitted to MoleQueue."
            )
            client.disconnect()
            self._remote_reset_buttons()
            return

        self.bar_var.set("MoleQueue: job submitted (ID={})".format(job_id))

        # ── Poll for status ───────────────────────────────────────────────
        terminal_states = {"Finished", "Error", "Canceled", "CanceledBeforeSubmission"}
        while True:
            time.sleep(5)
            status = client.get_job_status(job_id)
            if status is None:
                self.bar_var.set("MoleQueue: lost contact with daemon")
                self.queue_status.put("Fatal Error")
                break
            self.bar_var.set("MoleQueue: {}".format(status))
            if status in terminal_states:
                if status == "Finished":
                    self.queue_status.put("Finished!")
                else:
                    self.queue_status.put("Fatal Error")
                break

        client.disconnect()

    def _collect_input_files(self, s_params):
        """
        Returns a list of input file paths for the MoleQueue job.
        Adjust this method to match where Dynamics writes its input files.
        """
        import os
        # Try to get the working directory from s_params, fall back to home
        work_dir = os.getcwd()
        # Typical GROMACS input files produced by the Dynamics plugin
        candidates = [
            "{}.gro".format(s_params.project_name),
            "{}.top".format(s_params.project_name),
            "{}_em.tpr".format(s_params.project_name),
            "{}_md.tpr".format(s_params.project_name),
        ]
        files = []
        for name in candidates:
            full = os.path.join(work_dir, name)
            if os.path.exists(full):
                files.append(full)
        # Always return at least the working directory itself if nothing found
        if not files:
            files = [work_dir]
        return files

    def _remote_reset_buttons(self):
        """Re-enable Start buttons after a remote error."""
        self.stop_button.configure(state=DISABLED)
        self.start_button.configure(state=ACTIVE)
        if MOLEQUEUE_AVAILABLE:
            self.start_remote_button.configure(state=ACTIVE)

    # ─────────────────────────────────────────────
    # STATUS BAR
    # ─────────────────────────────────────────────

    def bar_update(self, s_params, status):
        percent = 0.0
        while s_params.stop:
            time.sleep(0.5)
        if percent != 100:
            time.sleep(0.5)
            percent = pymol_plugin_dynamics.steps_status_bar(0, s_params)
            self.queue_percent.put(percent)
            if s_params.stop == 0:
                self.queue_status.put(status[1])
            elif s_params.stop == 1:
                self.queue_status.put("User Stoped")

    def bar_display(self, root, parent, s_params):
        try:
            status = self.queue_status.get(block=False)
            self.bar_var.set(status)
        except Queue.Empty:
            status = "No change"

        try:
            percent = self.queue_percent.get(block=False)
            self.bar_widget.configure(value=percent)
        except:
            pass

        if status == "Fatal Error":
            self.start_counting(0, s_params)
            self.start_button.configure(state=DISABLED)
            tkMessageBox.showerror("GROMACS Error Message", "Error")
        if status == "Finished!":
            root.destroy()
            pymol_plugin_dynamics.show_interpretation_window(parent, s_params)
        else:
            root.after(100, self.bar_display, root, parent, s_params)