# jupyter-nbgrader-helper
## Installation
- clone repository
- python setup.py sdist
- pip install dist/nbhelper-\<VERSION\>.tar.gz

I probably won't add this to PyPI myself since it lacks polish and have no plans to update or maintain it outside of when I am using it, that being said, I don't see any of the functionality here breaking anytime soon.
## Usage
Override settings
- use these to change directories if you aren't using the default directory structure of nbgrader
- use ***select*** to perform a check or fix only on specific students

Fixing notebooks
- if you forgot to make your notebook into an assignment before releasing or have answers without nbgrader metadata (try not to do this!), use ***add***
- if you want to add extra test cells after releasing an assignment (you're better off adding empty test cells just in case and modifying them later), use ***add***
- if nbgrader autograde is complaining about test case points or duplicate grade_ids, use ***fix*** (and instruct students not to mess with cells)
- if there are other metadata issues with cells, use ***meta*** to fix assignment cells with the correct metadata from the source
- if there are still issues with the students notebook, use ***rmcells*** to remove everything not specifically part of the assignment
- if the notebook still won't autograde, use ***forcegrade*** (these won't appear in gradebook.db and feedback won't be generated from them)
- if you are having permission issues, use ***chmod*** (convenient wrapper to run chmod on all submissions)

Getting grades
- use the arguments under ***notebook checks*** after running nbgrader autograde and generate_feedback

Emailing feedback
- if you don't have an exchange setup, or your university has a policy against students viewing the grades and feedback of others (the feedback exchange is not private)
- use ***zip*** to collect all feedbacks
- use ***ckdir*** to test your command and folder structure
- replace ***ckdir*** with ***email*** in your command and follow the prompts

Backing up
- REMEMBER TO BACKUP YOUR NOTEBOOKS REGULARLY with ***backup***, submitted and source are most important

Deprecated features
- these probably still work, but aren't really useful
## Command Line Interface
```
usage: nbhelper.py [-h] [--nbhelp]
                   [--cdir path] [--sdir path] [--odir path]
                   [--add AssignName NbName.ipynb]
                   [--fix AssignName NbName.ipynb]
                   [--meta AssignName NbName.ipynb]
                   [--forcegrade AssignName NbName.ipynb]
                   [--sortcells AssignName NbName.ipynb]
                   [--rmcells AssignName NbName.ipynb]
                   [--select StudentID [StudentID ...]]
                   [--info AssignName]
                   [--moss AssignName] [--getmoss]
                   [--dist AssignName] [--fdist AssignName]
                   [--email AssignName|zip NbName.html|feedback.zip]
                   [--ckdir AssignName NbName.extension]
                   [--ckgrades AssignName]
                   [--ckdup NbName.extension]
                   [--chmod rwx AssignName]
                   [--avenue-collect submissions.zip AssignName]
                   [--zip AssignName [AssignName ...]]
                   [--zipfiles NbName.html [NbName.html ...]]
                   [--backup nbgrader_step]

A collection of helpful functions for use with jupyter nbgrader. Designed to
be placed in <course_dir>/nbhelper.py by default with the structure:
<course_dir>/<nbgrader_step>/[<student_id>/]<AssignName>/<NbName>.<ipynb|html>
where nbgrader_step = source|release|submitted|autograded|feedback

optional arguments:
  -h, --help            show this help message and exit
  --nbhelp              READ THIS FIRST

override settings:

  --cdir path           Override path to course_dir (default: current
                        directory)
  --sdir path           Override path to source directory
  --odir path           Override path to the submitted, autograded, or
                        feedback directory
  --select StudentID [StudentID ...]
                        Select specific students to fix their notebooks
                        without having to run on the entire class (WARNING:
                        moves student(s) to <course_dir>/nbhelper-select-tmp
                        then moves back unless an error was encountered)

notebook fixes:

  --add AssignName NbName.ipynb
                        Add missing nbgrader cell metadata and test cells to
                        submissions using the corresponding file in source as
                        a template by matching function names (python only),
                        template must be updated with nbgrader cells
  --fix AssignName NbName.ipynb
                        Update test points by using the corresponding file in
                        source as a template and matching the cell's grade_id,
                        also combines duplicate grade_ids
  --meta AssignName NbName.ipynb
                        Fix cell metadata by replacing with that of source,
                        matches based on grade_id
  --forcegrade AssignName NbName.ipynb
                        For particularly troublesome student notebooks that
                        fail so badly they don't even autograde or produce
                        proper error messages (you should run this command
                        with --select), this partially does autograders job:
                        combines the hidden test cases with the submission but
                        places it in <course_dir>/nbhelper-
                        autograde/<student_id>/<AssignName>/<NbName.ipynb>
                        then tries executing it via command line. You can also
                        run and test this notebook yourself, then move this
                        'autograded' notebook to the autograded directory and
                        use --dist to 'grade' it (make sure failed tests
                        retain their errors or they'll count as 'correct',
                        grades are not entered in gradebook.db)
  --sortcells AssignName NbName.ipynb
                        Sort cells of student notebooks to match order of
                        source, matches based on grade_id, non grade_id cells
                        are placed at the end
  --rmcells AssignName NbName.ipynb
                        MAKE SURE YOU BACKUP FIRST - Removes all student cells
                        that do not have a grade_id that matches the source
                        notebook (and sorts the ones that do) - this function
                        is destructive and should be used as a last resort
  --chmod rwx AssignName
                        Run chmod rwx on all submissions for an assignment
                        (linux only)

notebook checks:

  --moss AssignName     Exports student answer cells as files and optionally
                        check with moss using <course_dir>/moss/moss.pl
  --getmoss             Downloads moss script with your userid to
                        <course_dir>/moss/moss.pl then removes it after use
  --dist AssignName     Gets distribution of scores across test cells from
                        autograded notebooks and writes each student's results
                        to <course_dir>/reports/<AssignName>/dist-<NbName>.csv
  --fdist AssignName    Gets distribution of scores across test cells from
                        feedback (factoring in manual grading) and writes each
                        student's results to
                        <course_dir>/reports/<AssignName>/fdist-<NbName>.csv
  --ckdir AssignName NbName.extension
                        Check <course_dir>/feedback directory (change with
                        --odir) by printing studentIDs and matching files to
                        make sure it is structured properly
  --ckgrades AssignName
                        Checks for consistency between 'nbgrader export',
                        'dist', and 'fdist', and writes grades to
                        <course_dir>/reports/<AssignName>/grades-<NbName>.csv

notebook management:

  --email AssignName|zip NbName.html|feedback.zip
                        Email feedback to students (see EMAIL_CONFIG in
                        script, prompts for unset fields)
  --avenue-collect submissions.zip AssignName
                        Basically zip collect but tailored to avenue (LMS by
                        D2L), uses <course_dir>/classlist.csv to lookup
                        Student IDs using names from submissions, overwrites
                        submissions in submitted directory, backup first!
  --zip AssignName [AssignName ...]
                        Combine multiple feedbacks into
                        <course_dir>/feedback/<student_id>/zip/feedback.zip
  --zipfiles NbName.html [NbName.html ...]
                        Same as zip but matches files instead of assignment
                        folders
  --backup nbgrader_step
                        Backup nbgrader_step directory to
                        <course_dir>/backups/<nbgrader_step-mm-dd-hh-mm>.zip

deprecated features:

  --info AssignName     Get some quick info (student id, file size, cell
                        count, total execution count, [grade id : execution
                        count]) of all submissions and writes to
                        <course_dir>/reports/<AssignName>/info-<NbName>.csv
  --ckdup NbName.extension
                        Checks all submitted directories for NbName.extension
                        and reports subfolders containing multiple files of
                        the same extension

 ```
