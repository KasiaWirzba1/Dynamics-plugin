import pymol_plugin_dynamics
import queue as Queue
from tkinter import *
from tkinter.ttk import Progressbar, Scrollbar
import _thread as thread
import time
import os
from tkinter import messagebox as tkMessageBox

# MoleQueue integration
try:
    from MoleQueueClient import MoleQueueClient
    MOLEQUEUE_AVAILABLE = True
except ImportError:
    MOLEQUEUE_AVAILABLE = False

class CalculationWindow:
    """
    Window for running molecular dynamics calculations.
 
    Allows the user to choose between local execution (GROMACS runs directly
    on this machine) and remote execution (job is submitted to a MoleQueue
    daemon, which forwards it to a configured HPC queue).
 
    Communication between the background worker thread and the Tkinter UI
    is handled via two thread-safe queues: queue_status and queue_percent.
    """

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

    # WINDOW CREATION

    def check_window(self, master, g_parent, s_params, status):
        """
        Entry point called from the main plugin window when the user clicks OK.
        Destroys the main window and opens the mode selection dialog.
        Shows a warning if no molecule has been selected.
        """
        project_name = s_params.project_name
        if project_name != "nothing":
            master.destroy()
            self._ask_mode_and_open(g_parent, s_params, status)
        elif project_name == "nothing":
            pymol_plugin_dynamics.no_molecule_warning()

    def _ask_mode_and_open(self, g_parent, s_params, status):
        """
        Show a modal dialog asking the user to choose Local or Remote mode.
        Sets s_params.remote_mode accordingly and then opens the calculation window.
        The REMOTE button is disabled automatically if MoleQueueClient is not available.
        """
        dialog = Toplevel(g_parent)
        dialog.title("Choose Calculation Mode")
        dialog.resizable(False, False)
        dialog.grab_set()  # modal

        Label(dialog, text="Where do you want to run the simulation?",
              font=("Arial", 11), pady=10, padx=20).pack()

        btn_frame = Frame(dialog, pady=10)
        btn_frame.pack()

        def choose_local():
            s_params.remote_mode = False
            dialog.destroy()
            root = Toplevel(g_parent)
            self.window(root, s_params, status, g_parent)

        def choose_remote():
            if not MOLEQUEUE_AVAILABLE:
                tkMessageBox.showerror(
                    "MoleQueue not available",
                    "MoleQueueClient could not be imported.\n"
                    "Check if MoleQueueClient.py is in the plugin folder."
                )
                return
            s_params.remote_mode = True
            dialog.destroy()
            root = Toplevel(g_parent)
            self.window(root, s_params, status, g_parent)

        Button(btn_frame, text="LOCAL\n(this computer)",
               width=18, height=3,
               command=choose_local).pack(side=LEFT, padx=10)

        Button(btn_frame, text="REMOTE\n(via MoleQueue)",
               width=18, height=3,
               bg="#4A90D9", fg="white",
               activebackground="#357ABD", activeforeground="white",
               state=NORMAL if MOLEQUEUE_AVAILABLE else DISABLED,
               command=choose_remote).pack(side=LEFT, padx=10)

        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (dialog.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry("+{}+{}".format(x, y))

    def window(self, root, s_params, status, parent):
        """
        Build and display the main calculation window with progress bar and control buttons.
        """
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

        start_button = Button(frame2, text="START LOCAL",
                              command=lambda: self.start_counting(1, s_params))
        start_button.pack(side=LEFT)
        if stop == 0:
            start_button.configure(state=DISABLED)
        self.start_button = start_button

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

        tasks_nr = 0.0
        for task in s_params.progress.to_do:
            tasks_nr = tasks_nr + task
        self.tasks_to_do = tasks_nr

        thread.start_new_thread(self.bar_update, (s_params, status))
        self.bar_display(root, parent, s_params)

    # LOCAL EXECUTION

    def start_counting(self, value, s_params):
        """
        Start (value=1) or stop (value=0) a local GROMACS calculation.
        """
        if value == 1:
            thread.start_new_thread(pymol_plugin_dynamics.dynamics, (s_params,))
            self.stop_button.configure(state=ACTIVE)
            self.start_button.configure(state=DISABLED)
            self.start_remote_button.configure(state=DISABLED)
            self.log_button.configure(state=DISABLED)
        elif value == 0:
            self.stop_button.configure(state=DISABLED)
            self.start_button.configure(state=ACTIVE)
            if MOLEQUEUE_AVAILABLE:
                self.start_remote_button.configure(state=ACTIVE)
            self.log_button.configure(state=ACTIVE)

    # REMOTE EXECUTION via MoleQueue

    def start_counting_remote(self, s_params):
        """
        Initiate remote job submission via MoleQueue.
        Disables buttons and launches _remote_worker in a background thread.
        """
        self.stop_button.configure(state=ACTIVE)
        self.start_button.configure(state=DISABLED)
        self.start_remote_button.configure(state=DISABLED)
        self.log_button.configure(state=DISABLED)
        self.bar_var.set("Connecting to MoleQueue...")
        thread.start_new_thread(self._remote_worker, (s_params,))

    def _remote_worker(self, s_params):
        """
        Background thread — all communication with Tkinter goes through queue_status.
        Never calls bar_var.set() or tkMessageBox directly.
        1. Connects to the local MoleQueue daemon.
        2. Submits the job.
        3. Polls for status every 5 seconds.
        4. Puts the final status into queue_status so bar_display can react.
        """
        client = MoleQueueClient()

        if not client.connect():
            self.queue_status.put("MoleQueue Error: Cannot connect to MoleQueue daemon. Make sure MoleQueue is running.")
            return

        input_files = self._collect_input_files(s_params)

        job_id = client.submit_job(
            queue="Local",
            program="GROMACS",
            input_files=input_files,
            project_name=s_params.project_name
        )

        if not job_id:
            self.queue_status.put("MoleQueue Error: Job could not be submitted to MoleQueue.")
            client.disconnect()
            return

        self.queue_status.put("MoleQueue: job submitted (ID={})".format(job_id))

        terminal_states = {"Finished", "Error", "Canceled", "CanceledBeforeSubmission"}
        while True:
            time.sleep(5)
            status = client.get_job_status(job_id)
            if status is None:
                self.queue_status.put("Fatal Error")
                break
            self.queue_status.put("MoleQueue: {}".format(status))
            if status in terminal_states:
                if status == "Finished":
                    self.queue_status.put("Finished!")
                else:
                    self.queue_status.put("Fatal Error")
                break

        client.disconnect()

    def _collect_input_files(self, s_params):
        """
        Returns a list of GROMACS input file paths for the MoleQueue job.
        """
        work_dir = getattr(s_params, "work_dir", os.path.expanduser("~"))
        candidates = ["topol.tpr", "grompp.mdp", "topol.top", "conf.gro"]
        files = []
        for name in candidates:
            full = os.path.join(work_dir, name)
            if os.path.exists(full):
                files.append(full)
        if not files:
            files = [work_dir]
        return files

    # STATUS BAR

    def bar_update(self, s_params, status):
        """
        Background thread that monitors simulation progress.
        """
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
        """
        Tkinter-safe polling loop (runs in the main thread via root.after).
        Reads status and percent from the queues and updates the UI.
        """
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
            return
        elif status.startswith("MoleQueue Error"):
            self.stop_button.configure(state=DISABLED)
            self.start_button.configure(state=ACTIVE)
            if MOLEQUEUE_AVAILABLE:
                self.start_remote_button.configure(state=ACTIVE)
            tkMessageBox.showerror("MoleQueue Error", status.replace("MoleQueue Error: ", ""))
            return
        elif status == "Finished!":
            root.destroy()
            pymol_plugin_dynamics.show_interpretation_window(parent, s_params)
            return
        else:
            root.after(100, self.bar_display, root, parent, s_params)
