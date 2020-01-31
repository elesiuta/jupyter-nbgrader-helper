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

####### Config #######

EMAIL_CONFIG = {
    "EMAIL_DELAY": None, # time delay between sending each email in seconds
    "EMAIL_SUBJECT": None, # "email subject"
    "EMAIL_MESSAGE": "", # "email message text"
    "STUDENT_MAIL_DOMAIN": None, # "@domain.com"
    "MY_EMAIL_ADDRESS": None, # "myemail@domain.com"
    "MY_SMTP_SERVER": None, # "smtp.domain.com", script uses TLS on port 587
    "MY_SMTP_USERNAME": None, # "myusername"
    "MY_SMTP_PASSWORD": None # leave as None for prompt each time
}

NB_HELP = """
--Quick reference for nbgrader usage--
https://nbgrader.readthedocs.io/en/stable/user_guide/creating_and_grading_assignments.html
cd "course_directory"
# make sure the nbgrader toolbar and formgrader extensions are enabled
nbgrader assign "assignment_name" # creates the database entry and assignment folder
# create and edit the notebook(s) and any other files in source/assignment_name
# convert notebook into assignment with View -> Cell Toolbar -> Create Assignment
# mark necessary cells as 'Manually graded answer', 'Autograded answer', 'Autograder tests', and 'Read-only'
# validate the source notebook(s) then generate the student versions of the notebook(s)
nbgrader release "assignment_name" # release assignment to listed students through JupyterHub
nbgrader collect "assignment_name" # collect assignments submitted through JupyterHub
# can also be distributed and collected outside JupyterHub
nbgrader autograde "assignment_name"
# warning: only run the autograder in a VM or other restricted environment since python cannot be safely sandboxed
nbgrader feedback "assignment_name" # generates feedback (does not distribute it to students)
nbgrader export # exports grades as a csv file

--Workaround for getting errors on edits made after submissions received--
https://github.com/jupyter/nbgrader/issues/1069
nbgrader db assignment remove "assignment_name"
nbgrader db assignment add "assignment_name"
nbgrader assign "assignment_name"
do/apply edits
nbgrader release "assignment_name"
jupyter server may need to be restarted at any point during these steps

--If assignments have character encoding issues--
https://docs.python.org/3/library/codecs.html#error-handlers

--File names with spaces--
argparse does not escape spaces with '\\' in arguments, use \"double quotes\"

--Dependencies--
this script does not use any external libraries, however it depends on the JSON metadata format used by nbgrader https://nbgrader.readthedocs.io/en/stable/contributor_guide/metadata.html
all functions work on the ipynb/html files directly, it never touches the nbgrader database (gradebook.db)
"""


####### Generic functions #######

def writeCsv(fName, data, enc = None, delimiter = ","):
    os.makedirs(os.path.dirname(fName), exist_ok=True)
    with open(fName, "w", newline="", encoding=enc, errors="backslashreplace") as f:
        writer = csv.writer(f, delimiter=delimiter)
        for row in data:
            writer.writerow(row)

def readJson(fname):
    with open(fname, "r", errors="ignore") as json_file:  
        data = json.load(json_file)
    return data

def writeJson(fname, data):
    with open(fname, "w", errors="ignore") as json_file:  
        json.dump(data, json_file, indent=1, separators=(',', ': '))

def sendEmail(smtpServer, user, pwd, sender, recipient, subject, body = None, html = None, attachmentPath = None):
    email_user = user
    email_pwd = pwd
    message = email.message.EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Cc"] = sender
    message["Subject"] = subject
    if body != None:
        message.set_content(body)
        if html != None:
            message.add_alternative(html, subtype = "html")
    elif html != None:
        message.set_content(html, subtype = "html")
    if attachmentPath != None:
        filename = os.path.basename(attachmentPath)
        ctype, encoding = mimetypes.guess_type(attachmentPath)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(attachmentPath, 'rb') as fp:
            message.add_attachment(fp.read(),
                                   maintype=maintype,
                                   subtype=subtype,
                                   filename=filename)
    if type(smtpServer) == str:
        try:
            with smtplib.SMTP(smtpServer, port=587) as smtp_server:
                smtp_server.ehlo()
                smtp_server.starttls()
                smtp_server.login(email_user, email_pwd)
                smtp_server.send_message(message)
            return 0
        except Exception as e:
            print ("Failed to send mail %s to %s" %(subject, recipient))
            print (e)
            return 1
    else:
        try:
            smtpServer.send_message(message)
            return 0
        except Exception as e:
            print ("Failed to send mail %s to %s" %(subject, recipient))
            print (e)
            try:
                smtpServer.quit()
            except:
                pass
            return 1

####### Functions for applying functions #######

def applyTemplateSubmissions(func, template_path, submit_dir, file_name, assignment_name = None, delete = "n"):
    template = readJson(template_path)
    if os.path.isdir(submit_dir):
        for dirName, subdirList, fileList in os.walk(submit_dir):
            subdirList.sort()
            for f in sorted(fileList):
                fullPath = os.path.join(dirName, f)
                folder = os.path.basename(dirName)
                if (folder == assignment_name or assignment_name == None) and f == file_name:
                    studentID = os.path.split(os.path.split(os.path.split(fullPath)[0])[0])[1]
                    studentNB = readJson(fullPath)
                    studentNB = func(template, studentNB, studentID)
                    if studentNB != None:
                        writeJson(fullPath, studentNB)
                elif delete.lower() == "y":
                    os.remove(fullPath)

def applyFuncFiles(func, directory, file_name, *args):
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

def applyFuncDirectory(func, directory, assignment_name, file_name, file_extension, *args, **kwargs):
    output = []
    if os.path.isdir(directory):
        for dirName, subdirList, fileList in os.walk(directory):
            subdirList.sort()
            for f in sorted(fileList):
                fullPath = os.path.join(dirName, f)
                folder = os.path.basename(dirName)
                if folder == assignment_name:
                    if file_name == None or f == file_name:
                        if file_extension == None or f.split(".")[-1] == file_extension:
                            studentID = os.path.split(os.path.split(os.path.split(fullPath)[0])[0])[1]
                            output.append(func(fullPath, studentID, *args, **kwargs))
    return output

####### Helper functions #######

def getFunctionNames(source):
    function_names = []
    for line in source:
        if "def " in line:
            line = line.split(" ")
            function_name = line[line.index("def") + 1]
            function_name = function_name.split("(")[0]
            function_names.append(function_name)
    return function_names

def returnPath(fullPath, studentID):
    return {"student_id": studentID, "path": fullPath}

def printFileNames(fullPath, studentID):
    print("%s - %s" %(studentID, os.path.basename(fullPath)))

def getAnswerCells(fullPath, studentID):
    source_json = readJson(fullPath)
    output_string_list = []
    for cell in source_json["cells"]:
        try:
            if cell["metadata"]["nbgrader"]["locked"] == False:
                output_string_list += cell["source"]
        except:
            pass
    return {"student_id": studentID, "answers": output_string_list}

def concatNotebookAnswerCells(list_of_list_of_answer_dicts):
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

def getStudentFileDir(course_dir, odir, nbgrader_step):
    if odir == None:
        student_dir = os.path.join(course_dir, nbgrader_step)
    else:
        student_dir = os.path.normpath(odir)
    if not os.path.isdir(student_dir):
        sys.exit("Invalid directory: " + str(student_dir))
    return student_dir

def getAssignmentFiles(source_dir, assignment_name, file_extension, replace_file_extension = None):
    assignment_dir = os.path.join(source_dir, assignment_name)
    assignment_files = [f for f in os.listdir(assignment_dir) if os.path.splitext(f)[1][1:] == file_extension]
    if replace_file_extension == None:
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

####### Main functions #######

def addNbgraderCell(nbgrader, student, student_id = ""):
    last_answer_cell_index = 0
    found_student_cell = False
    modified = False
    for cell in nbgrader["cells"]:
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

def updateTestCells(template, student, student_id = ""):
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
                                temp = student["cells"][i]["metadata"]["nbgrader"].pop("points", None)
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
            temp = student["cells"].pop(i)
    # return updated notebook (probably still the same object but who cares)
    if modified:
        print("Updated test cells for:  " + student_id)
        return student
    else:
        print("No changes made for:     " + student_id)
        return None

def updateCellsMeta(template, student, student_id = ""):
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

def quickInfo(fullPath, studentID):
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

def checkDuplicates(fullPath, studentID):
    fDir, fName = os.path.split(fullPath)
    ext = fName.split(".")[-1]
    dupfiles = [f for f in os.listdir(fDir) if f.split(".")[-1] == ext]
    if len(dupfiles) > 1:
        for f in dupfiles:
            print("Warning (duplicate files found): %s - %s" %(studentID, f))
    else:
        print("%s - %s" %(studentID, fName))

def getAutogradedScore(fullPath, studentID):
    source_json = readJson(fullPath)
    pass_list = []
    points_list = []
    error_list = []
    grade_id_list = []
    for cell in source_json["cells"]:
        try:
            if cell["metadata"]["nbgrader"]["points"] >= 0:
                if cell["outputs"] == []:
                    pass_list.append(1)
                    error_list.append("No Error (passed test)")
                else:
                    pass_list.append(0)
                    if "ename" in cell["outputs"][0]:
                        error_list.append(cell["outputs"][0]["ename"])
                    else:
                        error_list.append("Other Error (failed test)")
                points_list.append(cell["metadata"]["nbgrader"]["points"])
                grade_id_list.append(cell["metadata"]["nbgrader"]["grade_id"])
        except:
            pass
    return {"student_id": studentID, "pass_list": pass_list, "points_list": points_list, "error_list": error_list, "grade_id_list": grade_id_list}

def getFeedbackScore(fullPath, studentID):
    with open(fullPath, 'r', errors='ignore') as f:
        source_html = f.readlines()
    score_list = []
    score_totals = []
    grade_id_list = []
    for line in source_html:
        try:
            if "Test cell</a> (Score" in line:
                space_split = line.split(" ")
                score_list.append(float(space_split[-3]))
                score_totals.append(float(space_split[-1].split(")")[0]))
                quote_split = line.split("\"")
                grade_id_list.append(quote_split[1][1:])
            elif " (Score: " in line:
                line = line.split(" ")
                total_score = float(line[line.index("(Score:")+1])
        except:
            print("Error for student: %s on line: %s" %(studentID, str(line)))
    return {"student_id": studentID, "total_score": total_score, "score_list": score_list, "score_totals": score_totals, "grade_id_list": grade_id_list}

def emailFeedback(feedbackHtmlPath, emailId, myEmailServer, myUser, myPassword, myEmail, studentMailDomain, subject):
    # with open(feedbackHtmlPath, "r", encoding="utf8", errors="replace") as f:
    #     feedbackHtml = f.read()
    msg = str(EMAIL_CONFIG["EMAIL_MESSAGE"])
    sendEmail(myEmailServer, myUser, myPassword, myEmail, emailId + studentMailDomain, subject, attachmentPath = feedbackHtmlPath, body = msg)
    time.sleep(float(EMAIL_CONFIG["EMAIL_DELAY"]))

def zipFeedback(student_dir, data):
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


####### Main #######

if __name__ == "__main__":
    readme = ("A collection of helpful functions for use with nbgrader, "
              "designed to be placed in <course_dir>/nbhelper.py (see https://nbgrader.readthedocs.io/en/stable/user_guide/philosophy.html) "
              "but can also be used offline or on alternative directories if you haven't been given proper access or want to easily test it in a safe environment")
    parser = argparse.ArgumentParser(description=readme)
    parser.add_argument("--cdir", type=str, metavar="path", default=os.getcwd(), dest="cdir",
                        help="Path to course directory (default: current directory) structured as <course_dir>/<nbgrader_step>/[<student_id>/]<AssignName>/<NbName>.<ipynb|html> where nbgrader_step = source|release|submitted|autograded|feedback")
    parser.add_argument("--sdir", type=str, metavar="path", default=None, dest="sdir",
                        help="Override path to source directory")
    parser.add_argument("--odir", type=str, metavar="path", default=None, dest="odir",
                        help="Override path to the submitted, autograded, or feedback directory")
    parser.add_argument("--add", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Add missing nbgrader cell metadata and test cells to submissions using the corresponding file in source as a template by matching function names, template must be updated with nbgrader cells")
    parser.add_argument("--fix", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Update test points by using the corresponding file in source as a template and matching the cell's grade_id, also combines duplicate grade_ids")
    parser.add_argument("--meta", type=str, metavar=("AssignName", "NbName.ipynb"), nargs=2,
                        help="Fix cell metadata by replacing with that of source, matches based on grade_id")
    parser.add_argument("--select", type=str, metavar="StudentID", nargs="*", default=[],
                        help="Select specific students to fix their notebooks without having to run on the entire class")
    parser.add_argument("--info", type=str, metavar="AssignName",
                        help="Get some quick info (student id, file size, cell count, total execution count, [grade id : execution count]) of all submissions and writes to <course_dir>/reports/<AssignName>/info-<NbName>.csv")
    parser.add_argument("--moss", type=str, metavar="AssignName",
                        help="Exports student answer cells as files and optionally check with moss using <course_dir>/moss/moss.pl")
    parser.add_argument("--dist", type=str, metavar="AssignName",
                        help="Gets distribution of scores across test cells from autograded notebooks and writes each student's results to <course_dir>/reports/<AssignName>/dist-<NbName>.csv")
    parser.add_argument("--fdist", type=str, metavar="AssignName",
                        help="Gets distribution of scores across test cells from feedback (factoring in manual grading) and writes each student's results to <course_dir>/reports/<AssignName>/fdist-<NbName>.csv")
    parser.add_argument("--email", type=str, metavar=("AssignName|zip", "NbName.html|feedback.zip"), nargs=2,
                        help="Email feedback to students (see config in script, prompts for unset fields)")
    parser.add_argument("--ckdir", type=str, metavar=("AssignName", "NbName.extension"), nargs=2,
                        help="Check <course_dir>/feedback directory (change with --odir) by printing studentIDs and matching files to make sure it is structured properly")
    parser.add_argument("--ckdup", type=str, metavar="NbName.extension", nargs="?",
                        help="Checks all submitted directories for NbName.extension and reports subfolders containing multiple files of the same extension")
    parser.add_argument("--zip", type=str, metavar="AssignName", nargs="+",
                        help="Combine multiple feedbacks into <course_dir>/feedback/<student_id>/zip/feedback.zip")
    parser.add_argument("--zipfiles", type=str, metavar="NbName.html", nargs="+",
                        help="Same as zip but matches files instead of assignment folders")
    parser.add_argument("--backup", type=str, metavar="nbgrader_step", choices=["autograded","feedback","release","source","submitted"],
                        help="Backup nbgrader_step directory to <course_dir>/backups/<nbgrader_step-mm-dd-hh-mm>.zip")
    parser.add_argument("--nbhelp", action="store_true",
                        help="Print quick reference for nbgrader and extra help")
    args = parser.parse_args()

    SCRIPT_DIR = os.getcwd()
    if os.path.isdir(args.cdir):
        COURSE_DIR = os.path.normpath(args.cdir)
    else:
        COURSE_DIR = None
        print("Invalid course directory: " + str(args.cdir))
    if args.sdir == None and COURSE_DIR != None:
        SOURCE_DIR = os.path.join(COURSE_DIR, "source")
    elif args.sdir != None:
        SOURCE_DIR = os.path.normpath(args.sdir)
    else:
        SOURCE_DIR = None
        print("Invalid source directory: " + str(args.sdir))

    if args.nbhelp:
        print(NB_HELP)

    if len(args.select) > 0:
        original_student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        args.odir = os.path.join(COURSE_DIR, "nbhelper-select-tmp")
        os.mkdir(args.odir)
        for student in args.select:
            shutil.move(os.path.join(original_student_dir, student), os.path.join(args.odir, student))

    if args.add != None:
        assign_name, nb_name = args.add
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(addNbgraderCell, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.fix != None:
        assign_name, nb_name = args.fix
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(updateTestCells, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.meta != None:
        assign_name, nb_name = args.meta
        template_path = os.path.join(SOURCE_DIR, assign_name, nb_name)
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        # if args.offline:
        #     delete = input("Delete other files (!=NbName.ipynb) from submission folder (y/N)? ")
        # else:
        #     delete = "n"
        applyTemplateSubmissions(updateCellsMeta, template_path, student_dir, nb_name, assign_name, delete="n")
        print("Done")

    if args.info != None:
        assign_name = args.info
        nb_names = getAssignmentFiles(SOURCE_DIR, assign_name, "ipynb")
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        for nb_name in nb_names:
            header = [["Student ID", "File Size", "Cell Count", "Total Execution Count", "[grade id : execution count]"]]
            data = applyFuncDirectory(quickInfo, student_dir, assign_name, nb_name, None)
            writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "info-" + os.path.splitext(nb_name)[0] + ".csv"), header + data)
        print("Done")

    if args.moss != None:
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
        wslCommand = "bash -c \"./%s\"" %(command)
        print(command)
        submit = input("execute command (y/N/wsl)? ")
        if submit.lower() == "y":
            os.system(command)
        elif submit.lower() == "wsl":
            os.system(wslCommand)
        os.chdir(SCRIPT_DIR)
        print("Done")

    if args.dist != None:
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

    if args.fdist != None:
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
                ad = "{:<4}".format(str(grade_dist[i]/len(grades)))
                print("Test Cell: %s Points: %s Total points: %s" %(cellnum, gp, gd))
            print("")
            writeCsv(os.path.join(COURSE_DIR, "reports", assign_name, "fdist-" + nb_name + ".csv"), data)
        print("Done")

    if args.email != None:
        assign_name, nb_name = args.email
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        for key in EMAIL_CONFIG:
            if EMAIL_CONFIG[key] == None:
                EMAIL_CONFIG[key] = input("Enter value for %s: " %(key))
        subject = EMAIL_CONFIG["EMAIL_SUBJECT"]
        studentMailDomain = EMAIL_CONFIG["STUDENT_MAIL_DOMAIN"]
        myEmailAddress = EMAIL_CONFIG["MY_EMAIL_ADDRESS"]
        myUser = EMAIL_CONFIG["MY_SMTP_USERNAME"]
        myPwd = EMAIL_CONFIG["MY_SMTP_PASSWORD"]
        myEmailServer = EMAIL_CONFIG["MY_SMTP_SERVER"]
        # smtp_server = smtplib.SMTP(myEmailServer, port=587)
        # smtp_server.ehlo()
        # smtp_server.starttls()
        # smtp_server.login(myUser, myPwd)
        applyFuncDirectory(emailFeedback, student_dir, assign_name, nb_name, None, myEmailServer, myUser, myPwd, myEmailAddress, studentMailDomain, subject)
        # smtp_server.quit()
        print("Done")

    if args.ckdir != None:
        assign_name, nb_name = args.ckdir
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        applyFuncDirectory(printFileNames, student_dir, assign_name, nb_name, None)
        print("Done")

    if args.ckdup != None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "submitted")
        applyFuncFiles(checkDuplicates, student_dir, args.ckdup)
        print("Done")

    if args.zip != None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        # get list of students and files
        data = []
        for assign_name in args.zip:
            data.append(applyFuncDirectory(returnPath, student_dir, assign_name, None, "html"))
        # use zip function
        zipFeedback(student_dir, data)
        print("Done")

    if args.zipfiles != None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, "feedback")
        # get list of students and files
        data = []
        for f in args.zipfiles:
            data.append(applyFuncFiles(returnPath, student_dir, f))
        # use zip function
        zipFeedback(student_dir, data)
        print("Done")
        
    if args.backup != None:
        student_dir = getStudentFileDir(COURSE_DIR, args.odir, args.backup)
        # prep backup
        backup_dir = os.path.join(COURSE_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        zip_name = args.backup + "-" + datetime.datetime.now().strftime("%m-%d-%H-%M")
        backup_name = os.path.join(backup_dir, zip_name)
        # backup
        shutil.make_archive(backup_name, "zip", student_dir)
        print("Done")

    if len(args.select) > 0:
        for student in args.select:
            shutil.move(os.path.join(args.odir, student), os.path.join(original_student_dir, student))
        os.rmdir(args.odir)


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

'''

