# BSD 3-Clause License

# Copyright (c) 2019, Eric Lesiuta
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import json
import os
import csv
import sys
import argparse
import collections
import smtplib
import email
import time
import datetime
import mimetypes
import zipfile
import shutil
import urllib.request
import typing
import glob
import re

####### Config #######

VERSION = "0.2.11"

EMAIL_CONFIG = {
    "CC_ADDRESS": None, # "ccemail@domain.com" or SELF to cc MY_EMAIL_ADDRESS
    "EMAIL_DELAY": None, # time delay between sending each email in seconds
    "EMAIL_SUBJECT": None, # "email subject"
    "EMAIL_MESSAGE": None, # "email message text"
    "EMAIL_HTML": None, # "email message html" or FEEDBACK
    "STUDENT_MAIL_DOMAIN": None, # "@domain.com"
    "MY_EMAIL_ADDRESS": None, # "myemail@domain.com"
    "MY_SMTP_SERVER": None, # "smtp.domain.com", script uses TLS on port 587
    "MY_SMTP_USERNAME": None, # "myusername"
    "MY_SMTP_PASSWORD": None # leave as None for prompt each time
}

NB_HELP = """
REMEMBER TO BACKUP THE SUBMITTED NOTEBOOKS REGULARLY
most of the course can be regenerated from these along with your source notebooks
you may also want to backup gradebook.db to save any manual grading (I think it's saved there, this script never touches it)
this script is designed to be as nondestructive as possible, most functions just read course files but some do make modifications to the submitted notebooks, trying for minimal modifications and only when necessary

--Quick reference for nbgrader usage--
# https://xkcd.com/293/
https://nbgrader.readthedocs.io/en/stable/user_guide/philosophy.html
https://nbgrader.readthedocs.io/en/stable/user_guide/creating_and_grading_assignments.html
https://nbgrader.readthedocs.io/en/stable/command_line_tools/index.html
# summary of steps
0.a) make sure the nbgrader toolbar and formgrader extensions are enabled (most actions can be performed from here)
0.b) otherwise, run all commands from the "course_directory"
1.a) create the assignment using formgrader
2.a) create and edit the notebook(s) and any other files in source/assignment_name
2.b) convert notebook into assignment with View -> Cell Toolbar -> Create Assignment
2.c) mark necessary cells as 'Manually graded answer', 'Autograded answer', 'Autograder tests', and 'Read-only'
3.a) validate the source notebook(s) then generate the student version of the notebook(s) (can be done through formgrader)
4.a) after releasing, only hidden test cells can be modified without workarounds or students refetching the assignment
4.b) release assignment through formgrader if using JupyterHub (places the generated student version in the outbound exchange folder)
4.c) collect assignments submitted through JupyterHub using formgrader (or use zip collect for external)
5. Autgrading and Feedback
$ nbgrader autograde "assignment_name" # warning: only run the autograder in restricted environments and backup submissions first
$ nbgrader generate_feedback "assignment_name" # just feedback in <0.6.0 (do not release, uses non-private outbound exchange folder)
$ nbgrader export # exports grades as a csv file

--Workaround for getting errors on assignment source edits made after submissions received--
https://github.com/jupyter/nbgrader/issues/1069
nbgrader db assignment remove "assignment_name"
nbgrader db assignment add "assignment_name"
nbgrader assign "assignment_name"
do/apply edits (generate)
nbgrader release "assignment_name"
jupyter server may need to be restarted at any point during these steps

--If assignments have character encoding issues--
https://docs.python.org/3/library/codecs.html#error-handlers

--File names with spaces--
argparse does not escape spaces with '\\' in arguments, use \"double quotes\"

--Dependencies--
this script does not use any external libraries, however it depends on the JSON metadata format used by jupyter https://nbformat.readthedocs.io/en/latest/format_description.html and nbgrader https://nbgrader.readthedocs.io/en/stable/contributor_guide/metadata.html
all functions work on the ipynb/html files directly, it never touches the nbgrader database (gradebook.db) or use the nbgrader api
this allows for more flexibility to repair notebooks nbgrader does not know how to handle and provides robustness in the event of mismatched versions or weird configuration changes by others

--Test Case Templates--
there are some useful templates in the comments at the bottom of the source code

--Version %s--
https://github.com/elesiuta/jupyter-nbgrader-helper
this software is licensed under the BSD 3-Clause License
""" %(VERSION)


####### Generic functions #######

def writeCsv(fName: str, data: list, enc = None, delimiter = ",") -> None:
    os.makedirs(os.path.dirname(fName), exist_ok=True)
    with open(fName, "w", newline="", encoding=enc, errors="backslashreplace") as f:
        writer = csv.writer(f, delimiter=delimiter)
        for row in data:
            writer.writerow(row)

def readCsv(fName: str, delimiter = ",") -> list:
    data = []
    with open(fName, "r", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            data.append(row)
    return data

def readJson(fname: str) -> dict:
    with open(fname, "r", errors="ignore") as json_file:  
        data = json.load(json_file)
    return data

def writeJson(fname: str, data: dict) -> None:
    if not os.path.isdir(os.path.dirname(fname)):
        os.makedirs(os.path.dirname(fname))
    with open(fname, "w", errors="ignore") as json_file:  
        json.dump(data, json_file, indent=1, separators=(',', ': '))

def sendEmail(smtp_server: typing.Union[str, smtplib.SMTP],
              smtp_user: str, smtp_pwd: str,
              sender: str, recipient: str,
              subject: str, 
              cc: typing.Union[str, None] = None,
              body: typing.Union[str, None] = None,
              html: typing.Union[str, None] = None,
              attachment_path: typing.Union[str, None] = None):
    message = email.message.EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    if cc is not None:
        message["Cc"] = cc
    message["Subject"] = subject
    if body is not None:
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype = "html")
    elif html is not None:
        message.set_content(html, subtype = "html")
    if attachment_path is not None:
        filename = os.path.basename(attachment_path)
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(attachment_path, 'rb') as fp:
            message.add_attachment(fp.read(),
                                   maintype=maintype,
                                   subtype=subtype,
                                   filename=filename)
    if type(smtp_server) == str:
        try:
            with smtplib.SMTP(smtp_server, port=587) as smtp_server_instance:
                smtp_server_instance.ehlo()
                smtp_server_instance.starttls()
                smtp_server_instance.login(smtp_user, smtp_pwd)
                smtp_server_instance.send_message(message)
            return True
        except Exception as e:
            print ("Failed to send mail %s to %s" %(subject, recipient))
            print (e)
            return False
    else:
        try:
            smtp_server.send_message(message)
            return True
        except Exception as e:
            print ("Failed to send mail %s to %s" %(subject, recipient))
            print (e)
            try:
                smtp_server.quit()
            except:
                pass
            return False


####### Functions for applying functions #######

def applyTemplateSubmissions(func, template_path: str, submit_dir: str, file_name: str, assignment_name = None, delete = "n", **kwargs) -> None:
    template = readJson(template_path)
    if os.path.isdir(submit_dir):
        for dirName, subdirList, fileList in os.walk(submit_dir):
            subdirList.sort()
            for f in sorted(fileList):
                fullPath = os.path.join(dirName, f)
                folder = os.path.basename(dirName)
                if (folder == assignment_name or assignment_name is None) and f == file_name:
                    studentID = os.path.split(os.path.split(os.path.split(fullPath)[0])[0])[1]
                    studentNB = readJson(fullPath)
                    studentNB = func(template, studentNB, studentID, **kwargs)
                    if studentNB is not None:
                        writeJson(fullPath, studentNB)
                elif delete.lower() == "y":
                    os.remove(fullPath)

def applyFuncFiles(func, directory: str, file_name: str, *args) -> list:
    output = []
    if os.path.isdir(directory):
        for dirName, subdirList, fileList in os.walk(directory):
            subdirList.sort()
            for f in sorted(fileList):
                fullPath = os.path.join(dirName, f)
                if f == file_name:
                    studentID = os.path.split(os.path.split(os.path.split(fullPath)[0])[0])[1]
                    output.append(func(fullPath, studentID, *args))
    return output

def applyFuncDirectory(func, directory: str, assignment_name: str, file_name: typing.Union[str, None], file_extension: typing.Union[str, None], *args, **kwargs) -> list:
    output = []
    if os.path.isdir(directory):
        for dirName, subdirList, fileList in os.walk(directory):
            subdirList.sort()
            for f in sorted(fileList):
                fullPath = os.path.join(dirName, f)
                folder = os.path.basename(dirName)
                if folder == assignment_name:
                    if file_name is None or f == file_name:
                        if file_extension is None or f.split(".")[-1] == file_extension:
                            studentID = os.path.split(os.path.split(os.path.split(fullPath)[0])[0])[1]
                            output.append(func(fullPath, studentID, *args, **kwargs))
    return output


####### Helper functions #######

def getFunctionNames(source: list) -> list:
    function_names = []
    for line in source:
        if "def " in line:
            line = line.split(" ")
            function_name = line[line.index("def") + 1]
            function_name = function_name.split("(")[0]
            function_names.append(function_name)
    return function_names

def returnPath(fullPath: str, studentID: str) -> dict:
    return {"student_id": studentID, "path": fullPath}

def printFileNames(fullPath: str, studentID: str) -> None:
    print("%s - %s" %(studentID, os.path.basename(fullPath)))

def getAnswerCells(fullPath: str, studentID: str) -> dict:
    source_json = readJson(fullPath)
    output_string_list = []
    for cell in source_json["cells"]:
        try:
            if cell["metadata"]["nbgrader"]["locked"] == False:
                output_string_list += cell["source"]
        except:
            pass
    return {"student_id": studentID, "answers": output_string_list}

def concatNotebookAnswerCells(list_of_list_of_answer_dicts) -> dict:
    answer_dict = {}
    for notebook_list in list_of_list_of_answer_dicts:
        for student_notebook in notebook_list:
            if student_notebook["student_id"] not in answer_dict:
                answer_dict[student_notebook["student_id"]] = student_notebook["answers"]
            else:
                answer_dict[student_notebook["student_id"]] += [""]
                answer_dict[student_notebook["student_id"]] += student_notebook["answers"]
    return answer_dict

def writeAnswerCells(answer_dict, codeDir):
    for student_id in answer_dict:
        codePath = os.path.join(codeDir, student_id + ".py")
        with open(codePath, "w", encoding="utf8", errors="backslashreplace") as f:
            f.writelines(answer_dict[student_id])

def getStudentFileDir(course_dir: str, odir: str, nbgrader_step: str) -> str:
    if odir is None:
        student_dir = os.path.join(course_dir, nbgrader_step)
    else:
        student_dir = os.path.normpath(odir)
    if not os.path.isdir(student_dir):
        sys.exit("Invalid directory: " + str(student_dir))
    return student_dir

def getAssignmentFiles(source_dir, assignment_name, file_extension, replace_file_extension = None):
    assignment_dir = os.path.join(source_dir, assignment_name)
    assignment_files = [f for f in os.listdir(assignment_dir) if os.path.splitext(f)[1][1:] == file_extension]
    if replace_file_extension is None:
        return assignment_files
    else:
        return [os.path.splitext(f)[0] + replace_file_extension for f in assignment_files]

def sortStudentGradeIds(student_dict, sorted_grade_id_list, grade_id_key = "grade_id_list"):
    sort_keys = sorted([key for key in student_dict if type(student_dict[key]) == list])
    other_keys = sorted([key for key in student_dict if type(student_dict[key]) != list])
    student_by_grade_id = dict(zip(student_dict[grade_id_key],zip(*[student_dict[key] for key in sort_keys])))
    new_student_dict = {}
    for key in sort_keys:
        new_student_dict[key] = [student_by_grade_id[grade_id][sort_keys.index(key)] for grade_id in sorted_grade_id_list]
    for key in other_keys:
        new_student_dict[key] = student_dict[key]
    return new_student_dict

def list2dict(list_of_dicts: list, unique_key: str):
    new_dict = {}
    for d in list_of_dicts:
        new_dict[d[unique_key]] = d
    return new_dict


####### Main functions #######

def sortStudentCells(template: dict, student: dict, student_id: str = "") -> typing.Union[dict, None]:
    # get template grade_id order
    template_grade_ids = []
    for cell in template["cells"]:
        try:
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            template_grade_ids.append(grade_id)
        except:
            pass
    # get student grade_id order
    student_grade_ids = []
    for cell in student["cells"]:
        try:
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            student_grade_ids.append(grade_id)
        except:
            pass
    # are changes necessary?
    if template_grade_ids == student_grade_ids:
        print("No changes made for:     " + student_id)
        return None
    else:
        new_student_cells = []
        # add all grade_id cells in order
        for grade_id in template_grade_ids:
            found_student_cell = False
            for cell in student["cells"]:
                try:
                    if cell["metadata"]["nbgrader"]["grade_id"] == grade_id:
                        found_student_cell = True
                        new_student_cells.append(cell)
                except:
                    pass
            if not found_student_cell:
                print("Student: %s is missing test cell: %s" %(student_id, grade_id))
        # re-add all non id cells to bottom
        for cell in student["cells"]:
            try:
                _ = cell["metadata"]["nbgrader"]["grade_id"]
            except:
                new_student_cells.append(cell)
        # return updated notebook (probably still the same object but who cares)
        print("Updated cell order for:  " + student_id)
        student["cells"] = new_student_cells
        return student

def removeNonEssentialCells(template: dict, student: dict, student_id: str = "") -> typing.Union[dict, None]:
    # get template grade_ids
    template_grade_ids = []
    for cell in template["cells"]:
        try:
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            template_grade_ids.append(grade_id)
        except:
            pass
    # start fresh, always modifies the notebook cells
    new_student_cells = []
    # add all grade_id cells in order
    for grade_id in template_grade_ids:
        found_student_cell = False
        for cell in student["cells"]:
            try:
                if cell["metadata"]["nbgrader"]["grade_id"] == grade_id:
                    found_student_cell = True
                    new_student_cells.append(cell)
                    break
            except:
                pass
        if not found_student_cell:
            print("Student: %s is missing test cell: %s" %(student_id, grade_id))
    # return updated notebook (probably still the same object but who cares)
    print("Updated notebook for:  " + student_id)
    student["cells"] = new_student_cells
    return student

def addNbgraderCell(template: dict, student: dict, student_id: str = "") -> typing.Union[dict, None]:
    last_answer_cell_index = 0
    found_student_cell = False
    modified = False
    for cell in template["cells"]:
        try:
            # answer cell
            if cell["metadata"]["nbgrader"]["locked"] == False:
                function_name = getFunctionNames(cell["source"])
                grade_id = cell["metadata"]["nbgrader"]["grade_id"]
                if function_name == []:
                    print("No function found: \n" + str(cell))
                    break
                # find student cell with matching grade_id first, then check functions
                found_student_cell = False
                for i in range(len(student["cells"])):
                    try:
                        if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == grade_id:
                            last_answer_cell_index = i
                            found_student_cell = True
                            break
                    except:
                        pass
                # no matching grade_id, now check functions
                if found_student_cell == False:
                    for i in range(len(student["cells"])):
                        try:
                            function_student = getFunctionNames(student["cells"][i]["source"])
                            # replace cell metadata if match
                            if any(f in function_student for f in function_name):
                                student["cells"][i]["metadata"] = cell["metadata"]
                                last_answer_cell_index = i
                                found_student_cell = True
                                modified = True
                                break
                        except:
                            pass
                # check student didn't mess up
                if found_student_cell == False:
                    print("Student function not found for: %s - %s" %(student_id, str(function_name)))
            # test cell
            elif cell["metadata"]["nbgrader"]["locked"] == True and found_student_cell:
                # check if test cell already exists
                grade_id = cell["metadata"]["nbgrader"]["grade_id"]
                found_test_cell = False
                for i in range(len(student["cells"])):
                    try:
                        if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == grade_id:
                            found_test_cell = True
                            break
                    except:
                        pass
                if found_test_cell == False:
                    # inset test cells after most recent answer cell
                    student["cells"].insert(last_answer_cell_index + 1, cell)
                    last_answer_cell_index += 1
                    modified = True
        except:
            pass
    if modified:
        print("Fixed notebook (added nbgrader metadata) for:   " + student_id)
        return student
    else:
        print("No changes made for:  " + student_id)
        return None

def updateTestCells(template: dict, student: dict, student_id: str = "") -> typing.Union[dict, None]:
    modified = False
    # update points in test cases
    for cell in template["cells"]:
        try:
            points = cell["metadata"]["nbgrader"]["points"]
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            found_student_cell = False
            for i in range(len(student["cells"])):
                try:
                    if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == grade_id:
                        found_student_cell = True
                        if student["cells"][i]["metadata"]["nbgrader"]["points"] != points:
                            student["cells"][i]["metadata"]["nbgrader"]["points"] = points
                            modified = True
                except:
                    pass
            if not found_student_cell:
                print("Student: %s is missing test cell: %s" %(student_id, grade_id))
        except:
            pass
    # make sure answer cells aren't graded
    for cell in template["cells"]:
        try:
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            if cell["metadata"]["nbgrader"]["grade"] == False and "points" not in cell["metadata"]["nbgrader"]:
                found_student_cell = False
                for i in range(len(student["cells"])):
                    try:
                        if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == grade_id:
                            found_student_cell = True
                            if student["cells"][i]["metadata"]["nbgrader"]["grade"] == True or "points" in student["cells"][i]["metadata"]["nbgrader"]:
                                student["cells"][i]["metadata"]["nbgrader"]["grade"] = False
                                _ = student["cells"][i]["metadata"]["nbgrader"].pop("points", None)
                                modified = True
                    except:
                        pass
                if not found_student_cell:
                    print("Student: %s is missing answer cell: %s" %(student_id, grade_id))
        except:
            pass
    # check for duplicate grade_ids, keep first one and concatenate contents of subsequent ones then remove them
    student_cells = {}
    remove_cells = []
    for i in range(len(student["cells"])):
        try:
            grade_id = student["cells"][i]["metadata"]["nbgrader"]["grade_id"]
            if grade_id in student_cells:
                student["cells"][student_cells[grade_id]]["source"] += student["cells"][i]["source"]
                remove_cells.append(i)
                modified = True
                print("Student: %s has duplicate answer cell: %s" %(student_id, grade_id))
            else:
                student_cells[grade_id] = i
        except:
            pass
    if len(remove_cells) > 0:
        for i in reversed(remove_cells):
            _ = student["cells"].pop(i)
    # return updated notebook (probably still the same object but who cares)
    if modified:
        print("Updated test cells for:  " + student_id)
        return student
    else:
        print("No changes made for:     " + student_id)
        return None

def updateCellsMeta(template: dict, student: dict, student_id: str = "") -> typing.Union[dict, None]:
    modified = False
    # update points in test cases
    for cell in template["cells"]:
        try:
            grade_id = cell["metadata"]["nbgrader"]["grade_id"]
            found_student_cell = False
            for i in range(len(student["cells"])):
                try:
                    if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == grade_id:
                        found_student_cell = True
                        if student["cells"][i]["cell_type"] != cell["cell_type"]:
                            student["cells"][i]["cell_type"] = cell["cell_type"]
                            modified = True
                        if student["cells"][i]["metadata"] != cell["metadata"]:
                            student["cells"][i]["metadata"] = cell["metadata"]
                            modified = True
                        if "outputs" not in student["cells"][i]:
                            student["cells"][i]["outputs"] = []
                            modified = True
                        if "execution_count" not in student["cells"][i]:
                            student["cells"][i]["execution_count"] = 0
                            modified = True
                except:
                    pass
            if not found_student_cell:
                print("Student: %s is missing test cell: %s" %(student_id, grade_id))
        except:
            pass
    # return updated notebook (probably still the same object but who cares)
    if modified:
        print("Updated cell metadata for:  " + student_id)
        return student
    else:
        print("No changes made for:     " + student_id)
        return None

def forceAutograde(template: dict, student: dict, student_id: str = "", course_dir = None, AssignName = None, NbNameipynb = None) -> typing.Union[dict, None]:
    for cell in template["cells"]:
        try:
            # test cell
            if cell["metadata"]["nbgrader"]["locked"] == True:
                found_test_cell = False
                for i in range(len(student["cells"])):
                    try:
                        if student["cells"][i]["metadata"]["nbgrader"]["grade_id"] == cell["metadata"]["nbgrader"]["grade_id"]:
                            found_test_cell = True
                            student["cells"][i] = cell
                            break
                    except:
                        pass
                if found_test_cell == False:
                    print("Missing test cells (fix with --add) for " + student_id)
        except:
            pass
    new_path = os.path.join(course_dir, "nbhelper-autograde", student_id, AssignName, NbNameipynb)
    writeJson(new_path, student)
    # https://nbconvert.readthedocs.io/en/latest/execute_api.html
    # https://nbconvert.readthedocs.io/en/latest/config_options.html
    # this is mostly just a quick hack for some rare edgecases, there's probably a more proper solution but most of the code to do this was already here for other reasons
    # using some of these flags with nbgrader might be enough to fix your issue
    command = "jupyter nbconvert --execute --ExecutePreprocessor.timeout=60 --ExecutePreprocessor.interrupt_on_timeout=True --ExecutePreprocessor.allow_errors=True --to notebook --inplace "
    os.system(command + new_path)
    return None

def quickInfo(fullPath: str, studentID: str):
    studentNB = readJson(fullPath)
    studentSize = os.path.getsize(fullPath)
    studentCells = len(studentNB["cells"])
    execution_count = sum(cell["execution_count"] for cell in studentNB["cells"] if "execution_count" in cell and type(cell["execution_count"]) == int)
    execution_by_id = []
    for cell in studentNB["cells"]:
        if "execution_count" in cell and "metadata" in cell:
            if "nbgrader" in cell["metadata"] and "grade_id" in cell["metadata"]["nbgrader"]:
                execution_by_id.append(str(cell["metadata"]["nbgrader"]["grade_id"]) + " : " + str(cell["execution_count"]))
    return [studentID, studentSize, studentCells, execution_count] + execution_by_id

def checkDuplicates(fullPath: str, studentID: str):
    fDir, fName = os.path.split(fullPath)
    ext = fName.split(".")[-1]
    dupfiles = [f for f in os.listdir(fDir) if f.split(".")[-1] == ext]
    if len(dupfiles) > 1:
        for f in dupfiles:
            print("Warning (duplicate files found): %s - %s" %(studentID, f))
    else:
        print("%s - %s" %(studentID, fName))

def getAutogradedScore(fullPath: str, studentID: str) -> dict:
    source_json = readJson(fullPath)
    pass_list = []
    points_list = []
    error_list = []
    grade_id_list = []
    for cell in source_json["cells"]:
        try:
            if cell["metadata"]["nbgrader"]["points"] >= 0:
                if (cell["outputs"] == [] or (
                    len(cell["outputs"]) >= 1 and
                    all([
                        (
                            "ename" not in cell_output and
                            "evalue" not in cell_output and
                            "traceback" not in cell_output and
                            ("output_type" in cell_output and
                            cell_output["output_type"] != "error") and
                            ("name" not in cell_output or
                            cell_output["name"] != "stderr")
                        )
                        for cell_output in cell["outputs"]
                    ])
                )):
                    pass_list.append(1)
                    error_list.append("No Error (passed test)")
                else:
                    pass_list.append(0)
                    found_error = False
                    for cell_output in cell["outputs"]:
                        if "ename" in cell_output:
                            error_list.append(cell_output["ename"])
                            found_error = True
                            break
                    if found_error == False:
                        error_list.append("Unknown Error (check outputs)")
                        print("Unexpected cell['outputs']: " + str(cell["outputs"]))
                points_list.append(cell["metadata"]["nbgrader"]["points"])
                grade_id_list.append(cell["metadata"]["nbgrader"]["grade_id"])
        except:
            pass
    return {"student_id": studentID, "pass_list": pass_list, "points_list": points_list, "error_list": error_list, "grade_id_list": grade_id_list}

def getFeedbackScore(fullPath: str, studentID: str) -> dict:
    with open(fullPath, 'r', errors='ignore') as f:
        source_html = f.readlines()
    score_list = []
    score_totals = []
    grade_id_list = []
    for line in source_html:
        match_score = re.search(r'\(Score: ?(\d+\.\d+) ?/ ?(\d+\.\d+)\)', line)
        if match_score:
            match_test_cell = re.search(r'<li><a href="#(.+?)">Test cell</a> ?\(Score: ?(\d+\.\d+) ?/ ?(\d+\.\d+)\)</li>', line)
            if match_test_cell:
                grade_id_list.append(match_test_cell.groups()[0])
                score_list.append(float(match_test_cell.groups()[1]))
                score_totals.append(float(match_test_cell.groups()[2]))
            else:
                total_score = float(match_score.groups()[0])
        # try:
        #     if "Test cell</a> (Score" in line:
        #         space_split = line.split(" ")
        #         score_list.append(float(space_split[-3]))
        #         score_totals.append(float(space_split[-1].split(")")[0]))
        #         quote_split = line.split("\"")
        #         grade_id_list.append(quote_split[1][1:])
        #     elif " (Score: " in line:
        #         line = line.split(" ")
        #         total_score = float(line[line.index("(Score:")+1])
        # except:
        #     print("Error for student: %s on line: %s" %(studentID, str(line)))
    return {"student_id": studentID, "total_score": total_score, "score_list": score_list, "score_totals": score_totals, "grade_id_list": grade_id_list}

def emailFeedback(feedback_html_path: str, student_email_id: str) -> list:
    if EMAIL_CONFIG["EMAIL_HTML"] == "FEEDBACK":
        with open(feedback_html_path, "r", encoding="utf8", errors="replace") as f:
            email_html = f.read()
        attachment_path = None
    else:
        email_html = EMAIL_CONFIG["EMAIL_HTML"]
        attachment_path = feedback_html_path
    success = sendEmail(EMAIL_CONFIG["MY_SMTP_SERVER"],
                        EMAIL_CONFIG["MY_SMTP_USERNAME"],
                        EMAIL_CONFIG["MY_SMTP_PASSWORD"],
                        EMAIL_CONFIG["MY_EMAIL_ADDRESS"],
                        student_email_id + EMAIL_CONFIG["STUDENT_MAIL_DOMAIN"],
                        EMAIL_CONFIG["EMAIL_SUBJECT"],
                        cc = EMAIL_CONFIG["CC_ADDRESS"],
                        attachment_path = attachment_path,
                        body = EMAIL_CONFIG["EMAIL_MESSAGE"],
                        html = email_html)
    time.sleep(float(EMAIL_CONFIG["EMAIL_DELAY"]))
    if success:
        print("Sent email to: " + student_email_id + EMAIL_CONFIG["STUDENT_MAIL_DOMAIN"])
        return [student_email_id, "1"]
    else:
        return [student_email_id, "0"]

def removeZips(fullPath: str, studentID: str) -> None:
    if os.path.isfile(fullPath):
        if os.path.split(fullPath)[1] == "feedback.zip":
            os.remove(fullPath)

def zipFeedback(student_dir: str, data: list) -> None:
    # convert to dict
    studentDict = {}
    for sub_list in data:
        for student in sub_list:
            if student["student_id"] not in studentDict:
                studentDict[student["student_id"]] = []
            studentDict[student["student_id"]].append(student["path"])
    # zip files into studentID/zip/feedback.zip
    for studentID in studentDict:
        zipPath = os.path.join(student_dir, studentID, "zip")
        os.makedirs(zipPath, exist_ok=True)
        with zipfile.ZipFile(os.path.join(zipPath, "feedback.zip"), 'w') as z:
            for f in studentDict[studentID]:
                z.write(f, os.path.basename(f))

def chmod(fullPath: str, studentID: str, permission: str) -> None:
    octal = eval("0o" + permission)
    os.chmod(fullPath, octal)
    new_permission = str(oct(os.stat(fullPath).st_mode))
    if new_permission[-len(permission):] != permission:
        os.system("chmod " + permission + " \"" + os.path.abspath(fullPath) + "\"")
        new_permission = str(oct(os.stat(fullPath).st_mode))
        if new_permission[-len(permission):] != permission:
            print("Could not change permissions for %s: %s" %(studentID, fullPath))

def readTimestamps(fullPath: str, studentID: str):
    try:
        with open(fullPath, 'r', errors='ignore') as f:
            timestamp = f.read()
        timestamp = re.search(r'([\d\-]+ ?[\d\.:]+)', timestamp)
        timestamp = timestamp.groups()[0]
    except:
        print("Could not read timestamp for %s" %(studentID))
        timestamp = "ERROR"
    return {"student_id": studentID, "read_timestamp": timestamp}


####### Main #######

def main():
    readme = ("A collection of helpful functions for use with jupyter nbgrader. "
              "Designed to be placed in <course_dir>/nbhelper.py by default with the structure: "
              "<course_dir>/<nbgrader_step>/[<student_id>/]<AssignName>/<NbName>.<ipynb|html> "
              "where nbgrader_step = source|release|submitted|autograded|feedback")
    parser = argparse.ArgumentParser(description=readme)
    parser.add_argument("--nbhelp", action="store_true",
                        help="READ THIS FIRST")
    parser.add_argument("--cdir", type=str, metavar="path", default=os.getcwd(), dest="cdir",
                        help="Override path to course_dir (default: current directory)")
    parser.add_argument("--sdir", type=str, metavar="path", default=None, dest="sdir",
                        help="Override path to source directory")
    parser.add_argument("--odir", type=str, metavar="path", default=None, dest="odir",
                        help="Override path to the submitted, autograded, or feedback directory")
    parser.add_argument("--add", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Add missing nbgrader cell metadata and test cells to submissions using the corresponding file in source as a template by matching function names (python only), template must be updated with nbgrader cells")
    parser.add_argument("--fix", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Update test points by using the corresponding file in source as a template and matching the cell's grade_id, also combines duplicate grade_ids")
    parser.add_argument("--meta", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Fix cell metadata by replacing with that of source, matches based on grade_id")
    parser.add_argument("--forcegrade", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="For particularly troublesome student notebooks that fail so badly they don't even autograde or produce proper error messages (you should run this command with --select), this partially does autograders job: combines the hidden test cases with the submission but places it in <course_dir>/nbhelper-autograde/<student_id>/<AssignName>/<NbName.ipynb> then tries executing it via command line. You can also run and test this notebook yourself, then move this 'autograded' notebook to the autograded directory and use --dist to 'grade' it (make sure failed tests retain their errors or they'll count as 'correct', grades are not entered in gradebook.db)")
    parser.add_argument("--sortcells", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Sort cells of student notebooks to match order of source, matches based on grade_id, non grade_id cells are placed at the end")
    parser.add_argument("--rmcells", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="MAKE SURE YOU BACKUP FIRST - Removes all student cells that do not have a grade_id that matches the source notebook (and sorts the ones that do) - this function is destructive and should be used as a last resort")
    parser.add_argument("--select", type=str, metavar="StudentID", nargs="+", default=None,
                        help="Select specific students to fix their notebooks without having to run on the entire class (WARNING: moves student(s) to <course_dir>/nbhelper-select-tmp then moves back unless an error was encountered)")
    parser.add_argument("--info", type=str, metavar="AssignName",
                        help="Get some quick info (student id, file size, cell count, total execution count, [grade id : execution count]) of all submissions and writes to <course_dir>/reports/<AssignName>/info-<NbName>.csv")
    parser.add_argument("--moss", type=str, metavar="AssignName",
                        help="Exports student answer cells as files and optionally check with moss using <course_dir>/moss/moss.pl")
    parser.add_argument("--getmoss", action="store_true",
                        help="Downloads moss script with your userid to <course_dir>/moss/moss.pl then removes it after use")
    parser.add_argument("--dist", type=str, metavar="AssignName",
                        help="Gets distribution of scores across test cells from autograded notebooks and writes each student's results to <course_dir>/reports/<AssignName>/dist-<NbName>.csv")
    parser.add_argument("--fdist", type=str, metavar="AssignName",
                        help="Gets distribution of scores across test cells from feedback (factoring in manual grading) and writes each student's results to <course_dir>/reports/<AssignName>/fdist-<NbName>.csv")
    parser.add_argument("--email", type=str, metavar=("AssignName|zip", "NbName.html|feedback.zip"), nargs=2,
                        help="Email feedback to students (see EMAIL_CONFIG in script, prompts for unset fields)")
    parser.add_argument("--ckdir", type=str, metavar=("AssignName", "NbName.extension"), nargs=2,
                        help="Check <course_dir>/feedback directory (change with --odir) by printing studentIDs and matching files to make sure it is structured properly")
    parser.add_argument("--ckgrades", type=str, metavar="AssignName",
                        help="Checks for consistency between 'nbgrader export', 'dist', and 'fdist', and writes grades to <course_dir>/reports/<AssignName>/grades-<NbName>.csv")
    parser.add_argument("--ckdup", type=str, metavar="NbName.extension",
                        help="Checks all submitted directories for NbName.extension and reports subfolders containing multiple files of the same extension")
    parser.add_argument("--chmod", type=str, metavar=("rwx", "AssignName"), nargs=2,
                        help="Run chmod rwx on all submissions for an assignment (linux only)")
    parser.add_argument("--avenue-collect", dest="avenue_collect", type=str, metavar=("submissions.zip", "AssignName"), nargs=2,
                        help="Basically zip collect but tailored to avenue (LMS by D2L), uses <course_dir>/classlist.csv to lookup Student IDs using names from submissions, overwrites submissions in submitted directory, backup first!")
    parser.add_argument("--zip", type=str, metavar="AssignName", nargs="+",
                        help="Combine multiple feedbacks into <course_dir>/feedback/<student_id>/zip/feedback.zip")
    parser.add_argument("--zipfiles", type=str, metavar="NbName.html", nargs="+",
                        help="Same as zip but matches files instead of assignment folders")
    parser.add_argument("--backup", type=str, metavar="nbgrader_step", choices=["autograded","feedback","release","source","submitted"],
                        help="Backup nbgrader_step directory to <course_dir>/backups/<nbgrader_step-mm-dd-hh-mm>.zip")
    args = parser.parse_args()

    SCRIPT_DIR = os.getcwd()
    if os.path.isdir(args.cdir):
        COURSE_DIR = os.path.normpath(args.cdir)
    else:
        COURSE_DIR = None
        print("Invalid course directory: " + str(args.cdir))
    if args.sdir is None and COURSE_DIR is not None:
        SOURCE_DIR = os.path.join(COURSE_DIR, "source")
    elif args.sdir is not None:
        SOURCE_DIR = os.path.normpath(args.sdir)
    else:
        SOURCE_DIR = None
        print("Invalid source directory: " + str(args.sdir))

    if args.nbhelp:
        print(NB_HELP)

    if args.select is not None:
        original_student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        args.odir = os.path.join(COURSE_DIR, "nbhelper-select-tmp")
        os.mkdir(args.odir)
        for student in args.select:
            shutil.move(os.path.join(original_student_dir, student), os.path.join(args.odir, student))

    if args.getmoss == True:
        req = urllib.request.urlopen("http://moss.stanford.edu/general/scripts/mossnet")
        moss_script = req.read().decode()
        userid = input("Enter your moss userid: ")
        moss_script = moss_script.replace("$userid=987654321;", "$userid=%s;" %(userid))
        os.makedirs(os.path.join(COURSE_DIR, "moss"), exist_ok=True)
        if os.name == "nt":
            with open(os.path.join(COURSE_DIR, "moss", "moss.pl"), "w") as f:
                f.write(moss_script)
        else:
            with os.fdopen(os.open(os.path.join(COURSE_DIR, "moss", "moss.pl"), os.O_CREAT | os.O_RDWR, 0o700), "w") as f:
                f.write(moss_script)

    if args.add is not None:
        assign_name, nb_name = args.add
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(addNbgraderCell, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.fix is not None:
        assign_name, nb_name = args.fix
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(updateTestCells, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.meta is not None:
        assign_name, nb_name = args.meta
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(updateCellsMeta, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.forcegrade is not None:
        assign_name, nb_name = args.forcegrade
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(forceAutograde, template_path, student_dir, nb_name, assign_name, delete="n", course_dir = COURSE_DIR, AssignName = assign_name, NbNameipynb = nb_name)
        print("Done")

    if args.sortcells is not None:
        assign_name, nb_name = args.sortcells
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(sortStudentCells, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.rmcells is not None:
        assign_name, nb_name = args.rmcells
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(removeNonEssentialCells, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.info is not None:
        assign_name = args.info
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        for nb_name in nb_names:
            header = [["Student ID", "File Size", "Cell Count", "Total Execution Count", "[grade id : execution count]"]]
            data = applyFuncDirectory(quickInfo, student_dir, assign_name, nb_name, None)
            writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "info-" + os.path.splitext(nb_name)[0] + ".csv"), header + data)
        print("Done")

    if args.chmod is not None:
        assign_name = args.chmod[1]
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        for nb_name in nb_names:
            applyFuncDirectory(chmod, student_dir, assign_name, nb_name, None, args.chmod[0])
        print("Done")

    if args.moss is not None:
        assign_name = args.moss
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # prep directory
        assignment = assign_name.replace(" ", "_")
        codeDir = os.path.join(COURSE_DIR, "moss", assignment)
        os.makedirs(codeDir, exist_ok=True)
        # extract code from student notebooks
        data = []
        for nb_name in nb_names:
            data.append(applyFuncDirectory(getAnswerCells, student_dir, assign_name, nb_name, None))
        clean_data = concatNotebookAnswerCells(data)
        writeAnswerCells(clean_data, codeDir)
        # prepare to submit to MOSS
        command = "moss.pl -l python " + assignment + "/*.py"
        # construct base file
        try:
            data = []
            for nb_name in nb_names:
                template = os.path.join(SOURCE_DIR, assign_name, nb_name)
                data.append([getAnswerCells(template, "instructor")])
            clean_data = concatNotebookAnswerCells(data)
            baseCode = clean_data["instructor"]
            # remove solution blocks
            baseCodeClean = []
            nonSolution = True
            for line in baseCode:
                if "### BEGIN SOLUTION" in line:
                    nonSolution = False
                elif "### END SOLUTION" in line:
                    nonSolution = True
                elif nonSolution:
                    baseCodeClean.append(line)
            baseFile = os.path.join(COURSE_DIR, "moss", assignment + "-base.py")
            with open(baseFile, "w", encoding="utf8", errors="backslashreplace") as f:
                f.writelines(baseCodeClean)
            command = "moss.pl -l python -b %s %s/*.py" %(assignment + "-base.py", assignment)
        except:
            print("Failed to construct base file")
        # execute command
        os.chdir(os.path.join(COURSE_DIR, "moss"))
        if os.name == "nt":
            wslCommand = "bash -c \"./%s\"" %(command)
            print(command)
            submit = input("execute command (y/N/wsl)? ")
            if submit.lower() == "y":
                os.system(command)
            elif submit.lower() == "wsl":
                os.system(wslCommand)
        else:
            command = "./" + command
            print(command)
            submit = input("execute command (y/N)? ")
            if submit.lower() == "y":
                os.system(command)
        os.chdir(SCRIPT_DIR)
        print("Done")

    if args.dist is not None:
        assign_name = args.dist
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "autograded")
        for nb_name in nb_names:
            print("Distribution for " + nb_name)
            # Init variables
            source_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
            grade_id_list = getAutogradedScore(source_path, "instructor")["grade_id_list"]
            grade_points = getAutogradedScore(source_path, "instructor")["points_list"]
            grade_dist = [0] * len(grade_points)
            error_list = [[] for i in range(len(grade_points))]
            data = [["Test Cell"] + [i for i in range(1,len(grade_points)+1)]]
            data.append(["Cell ID"] + grade_id_list)
            data.append(["Points"] + grade_points)
            # Get grades
            grades = applyFuncDirectory(getAutogradedScore, student_dir, assign_name, nb_name, None)
            # getAutogradedScore().keys() -> ["student_id", "pass_list", "points_list", "error_list", "grade_id_list"]
            # Get distribution
            for student in grades:
                # check order
                if grade_id_list != student["grade_id_list"]:
                    a, b = grade_id_list, student["grade_id_list"]
                    if all([i in a and j in b for i in b for j in a]):
                        student = sortStudentGradeIds(student, grade_id_list)
                        print("Grade IDs were out of order for: " + student["student_id"])
                # check if grade ids match now
                if grade_id_list == student["grade_id_list"]:
                    data.append([student["student_id"]] + student["pass_list"])
                    for i in range(len(grade_points)):
                        grade_dist[i] += student["pass_list"][i]
                        error_list[i].append(student["error_list"][i])
                else:
                    # still something wrong
                    print(student["student_id"] + " has something wrong with their notebook")
                    print(student)
            print("Total students: " + str(len(error_list[0])))
            for i in range(len(grade_points)):
                cellnum = "{:<5}".format(str(i+1))
                gp = "{:<4}".format(str(grade_points[i]))
                gd = "{:<4}".format(str(grade_dist[i]))
                print("Test Cell: %s Points: %s Total passes: %s" %(cellnum, gp, gd))
            print("")
            for i in range(len(grade_points)):
                print("Errors for test cell: %s" %(i+1))
                print(collections.Counter(error_list[i]))
                print("")
            writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "dist-" + os.path.splitext(nb_name)[0] + ".csv"), data)
        print("Done")

    if args.fdist is not None:
        assign_name = args.fdist
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb", "")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        for nb_name in nb_names:
            print("Distribution for " + nb_name + ".html")
            # Init variables
            source_path = os.path.join(SOURCE_DIR, assign_name, nb_name + ".ipynb")
            grade_id_list = getAutogradedScore(source_path, "instructor")["grade_id_list"]
            grade_points = getAutogradedScore(source_path, "instructor")["points_list"]
            grade_dist = [0.0] * len(grade_points)
            data = [["Test Cell"] + [i for i in range(1,len(grade_points)+1)]]
            data.append(["Cell ID"] + grade_id_list)
            data.append(["Points"] + grade_points)
            # Get grades
            grades = applyFuncDirectory(getFeedbackScore, student_dir, assign_name, nb_name + ".html", None)
            # getFeedbackScore().keys() -> ["student_id", "total_score", "score_list", "score_totals", "grade_id_list"]
            # Get distribution
            for student in grades:
                # check order
                if grade_id_list != student["grade_id_list"]:
                    a, b = grade_id_list, student["grade_id_list"]
                    if all([i in a and j in b for i in b for j in a]):
                        student = sortStudentGradeIds(student, grade_id_list)
                        print("Grade IDs were out of order for: " + student["student_id"])
                # check if grade ids match now and for other possible errors
                if grade_id_list == student["grade_id_list"] and grade_points == student["score_totals"] and abs(student["total_score"] - sum(student["score_list"])) < 0.1:
                    data.append([student["student_id"]] + student["score_list"])
                    for i in range(len(grade_points)):
                        grade_dist[i] += student["score_list"][i]
                else:
                    print(student["student_id"] + " has something wrong with their feedback")
                    print(student)
            print("Total students: " + str(len(grades)))
            for i in range(len(grade_points)):
                cellnum = "{:<5}".format(str(i+1))
                gp = "{:<4}".format(str(grade_points[i]))
                gd = "{:<4}".format(str(grade_dist[i]))
                _ad = "{:<4}".format(str(grade_dist[i]/len(grades)))
                print("Test Cell: %s Points: %s Total points: %s" %(cellnum, gp, gd))
            print("")
            writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "fdist-" + nb_name + ".csv"), data)
        print("Done")

    if args.ckgrades is not None:
        assign_name = args.ckgrades
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        grade_dict = {}
        # check nbgrader grades
        nbgrader_grades = readCsv(os.path.join(COURSE_DIR, "grades.csv"))
        for row in nbgrader_grades:
            if row[0] == assign_name:
                student_id = row[3]
                grade_dict[student_id] = {
                    "timestamp": row[2],
                    "read_timestamp": 0,
                    "raw_score": float(row[7]),
                    "score": float(row[9]),
                    "dist_score": 0,
                    "fdist_score": 0
                }
        # check timestamps
        timestamps = applyFuncDirectory(readTimestamps, student_dir, assign_name, "timestamp.txt", None)
        for ts in timestamps:
            if ts["student_id"] not in grade_dict:
                print(ts["student_id"] + " has a submission timestamp but no recorded grade????")
                grade_dict[student_id] = {
                    "timestamp": "",
                    "read_timestamp": "",
                    "raw_score": 0,
                    "score": 0,
                    "dist_score": 0,
                    "fdist_score": 0
                }
            grade_dict[ts["student_id"]]["read_timestamp"] = ts["read_timestamp"]
        # check dist (grades obtained from autograded notebooks)
        for nb in glob.glob(os.path.join(COURSE_DIR, "reports", assign_name, "dist-*.csv")):
            nb = readCsv(nb)
            points = nb[2]
            for row in nb[3:]:
                if row[0] not in grade_dict:
                    grade_dict[student_id] = {
                        "timestamp": "",
                        "read_timestamp": "",
                        "raw_score": 0,
                        "score": 0,
                        "dist_score": 0,
                        "fdist_score": 0
                    }
                grade_dict[row[0]]["dist_score"] += sum([float(i) * float(j) for i, j in zip(points[1:], row[1:])])
        # check fdist (grades obtained from generated feedback)
        for nb in glob.glob(os.path.join(COURSE_DIR, "reports", assign_name, "fdist-*.csv")):
            nb = readCsv(nb)
            points = nb[2]
            for row in nb[3:]:
                if row[0] not in grade_dict:
                    grade_dict[student_id] = {
                        "timestamp": "",
                        "read_timestamp": "",
                        "raw_score": 0,
                        "score": 0,
                        "dist_score": 0,
                        "fdist_score": 0
                    }
                grade_dict[row[0]]["fdist_score"] += sum([float(i) for i in row[1:]])
        # compare and export grades
        grade_list = [["student_id", assign_name, "timestamp"]]
        for student_id in grade_dict.keys():
            if (grade_dict[student_id]["raw_score"] != grade_dict[student_id]["dist_score"] or
                grade_dict[student_id]["score"] != grade_dict[student_id]["fdist_score"]):
                # I think raw_score is purely autograded and score reflects manual grading, but could be wrong and they both reflect manual
                print(student_id + " grades don't match: " + str(grade_dict[student_id]))
                grade_list.append([student_id, grade_dict[student_id]["score"], grade_dict[student_id]["timestamp"], "ERROR", str(grade_dict[student_id])])
            elif (grade_dict[student_id]["timestamp"] is not None and 
                  len(str(grade_dict[student_id]["timestamp"])) > 0 and
                  str(grade_dict[student_id]["timestamp"]).strip() != str(grade_dict[student_id]["read_timestamp"]).strip()):
                print(student_id + " timestamps don't match: " + str(grade_dict[student_id]))
                grade_list.append([student_id, grade_dict[student_id]["score"], grade_dict[student_id]["timestamp"], "ERROR", str(grade_dict[student_id])])
            else:
                grade_list.append([student_id, grade_dict[student_id]["score"], grade_dict[student_id]["timestamp"]])
        writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "ckdgrades.csv"), grade_list)
        print("Done")

    if args.email is not None:
        assign_name, nb_name = args.email
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        for key in EMAIL_CONFIG:
            if EMAIL_CONFIG[key] is None:
                EMAIL_CONFIG[key] = input("Enter value for %s: " %(key))
                # replace blank entries with None
                if EMAIL_CONFIG[key].strip() == "":
                    EMAIL_CONFIG[key] = None
        if EMAIL_CONFIG["CC_ADDRESS"] == "SELF":
            EMAIL_CONFIG["CC_ADDRESS"] = EMAIL_CONFIG["MY_EMAIL_ADDRESS"]
        # smtp_server = smtplib.SMTP(EMAIL_CONFIG["MY_SMTP_SERVER"], port=587)
        # smtp_server.ehlo()
        # smtp_server.starttls()
        # smtp_server.login(myUser, myPwd)
        # EMAIL_CONFIG["MY_SMTP_SERVER"] = smtp_server
        log = applyFuncDirectory(emailFeedback, student_dir, assign_name, nb_name, None)
        # smtp_server.quit()
        header = [["Student ID", "Email Sent"]]
        writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "email-" + nb_name + "-" + datetime.datetime.now().strftime("%m-%d-%H-%M") + ".csv"), header + log)
        print("Done")

    if args.ckdir is not None:
        assign_name, nb_name = args.ckdir
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        none_list = applyFuncDirectory(printFileNames, student_dir, assign_name, nb_name, None)
        print("Found %s files" %(len(none_list)))
        print("Done")

    if args.ckdup is not None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        applyFuncFiles(checkDuplicates, student_dir, args.ckdup)
        print("Done")

    if args.avenue_collect is not None:
        zip_file, assign_name = args.avenue_collect
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        tmp_dir = os.path.join(COURSE_DIR, "nbhelper-avenue-tmp")
        classlist = os.path.join(COURSE_DIR, "classlist.csv")

        # create lookup dictionary for students
        import csv
        student_dictionary = {}
        with open(classlist, "r") as f:
            classlist = list(csv.reader(f))
        for row in classlist[1:]:
            student_name = " ".join([row[3], row[2]])
            student_id = str(row[4])
            student_dictionary[student_name] = student_id

        # rename and move submissions
        log = []
        shutil.unpack_archive(zip_file, tmp_dir)
        submission_list = os.listdir(tmp_dir)
        for submission in submission_list:
            try:
                log.append([submission])
                student_name = submission.split(" - ")[1]
                student_id = student_dictionary[student_name]
                # file_name = submission.split(" - ")[-1]
                file_name = "%s.ipynb" %(assign_name)
                current_path = os.path.join(tmp_dir, submission)
                new_path = os.path.join(student_dir, student_id, assign_name, file_name)
                if not os.path.isdir(os.path.dirname(new_path)):
                    os.makedirs(os.path.dirname(new_path))
                shutil.move(current_path, new_path)
                # time_stamp_path = os.path.join(student_dir, student_id, assign_name, "timestamp.txt")
                # with open(time_stamp_path, "w") as f:
                #     f.write("1970-01-01 00:00:00.000000 UTC")
                log[-1] += [student_id, file_name, "SUCCESS"]
            except:
                log[-1] += ["","","FAILURE"]

        writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "avenue-collect-" + datetime.datetime.now().strftime("%m-%d-%H-%M") + ".csv"), log)
        print("Done")

    if args.zip is not None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        # get list of students and files
        data = []
        for assign_name in args.zip:
            data.append(applyFuncDirectory(returnPath, student_dir, assign_name, None, "html"))
        # use zip function
        applyFuncDirectory(removeZips, student_dir, "zip", "feedback.zip", None)
        zipFeedback(student_dir, data)
        print("Done")

    if args.zipfiles is not None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        # get list of students and files
        data = []
        for f in args.zipfiles:
            data.append(applyFuncFiles(returnPath, student_dir, f))
        # use zip function
        applyFuncDirectory(removeZips, student_dir, "zip", "feedback.zip", None)
        zipFeedback(student_dir, data)
        print("Done")
        
    if args.backup is not None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, args.backup)
        # prep backup
        backup_dir = os.path.join(COURSE_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        zip_name = args.backup + "-" + datetime.datetime.now().strftime("%m-%d-%H-%M")
        backup_name = os.path.join(backup_dir, zip_name)
        # backup
        shutil.make_archive(backup_name, "zip", student_dir)
        print("Done")

    if args.getmoss == True:
        os.remove(os.path.join(COURSE_DIR, "moss", "moss.pl"))

    if args.select is not None:
        for student in args.select:
            shutil.move(os.path.join(args.odir, student), os.path.join(original_student_dir, student))
        os.rmdir(args.odir)

if __name__ == "__main__":
    sys.exit(main())


####### Templates #######

'''
##### Recursion #####

### BEGIN SOLUTION
def fib(n):
    # base case
    if n == 0:
        return 1
    if n == 1:
        return 1
    # common case
    return fib(n-1) + fib(n-2)
### END SOLUTION

### BEGIN HIDDEN TESTS
def recursionChecker(func):
    recursion_counter = [0]
    def wrapper(*args):
        recursion_counter[0] += 1
        return func(*args)
    return wrapper, recursion_counter
fib, recursion_counter = recursionChecker(fib)
assert fib(10) == 89
assert recursion_counter[0] > 10
### END HIDDEN TESTS

##### Limit Execution Time #####

### BEGIN SOLUTION
def fibLoop(n):
    terms = [1,1]
    for i in range(n-1):
        terms.append(terms[-1] + terms[-2])
    return terms[-1]
### END SOLUTION

### BEGIN HIDDEN TESTS
def asyncAssertAnswer():
    # put original test case(s) here
    assert fibLoop(10) == 89
from multiprocessing import Pool
if __name__ == '__main__':
    with Pool(processes=1) as pool:
        res = pool.apply_async(asyncAssertAnswer)
        res.get(timeout=10)
### END HIDDEN TESTS

##### Semi-Hidden Test Cases #####

### BEGIN SOLUTION
def gcd(a, b):
    a, b = abs(a), abs(b)
    while b != 0:
        a, b = b, a % b
    return a
### END SOLUTION

### Test Cases
from hashlib import sha256
hash_fun = lambda x : sha256(str(x).encode()).hexdigest()
# visible input, hidden output
assert hash_fun(gcd(30, 42)) == 'e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683'
# semi-hidden input, hidden output, chance of false positives
inputs = [(x,y) for x in range(50) for y in range (50)]
assert any([hash_fun(gcd(*x)) == 'e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683' for x in inputs])

##### Checking Implimentation #####

https://nbgrader.readthedocs.io/en/stable/user_guide/autograding_resources.html#checking-whether-a-specific-function-has-been-used
# read previous cell(s) as string by checking lists In or _ih, or using history magics
# this is less reliable if the student overwrites those variables
# or cells are out of order (might add a function that can check/fix that), nbgrader should only run student answer cells and test case cells
%history -f history.txt
with open("history.txt", "r") as f:  
    history = f.read()

'''

