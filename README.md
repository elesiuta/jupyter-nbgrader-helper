# jupyter-nbgrader-helper

```
usage: nbhelper.py [-h] [--nbhelp] 
                   [--cdir path] [--sdir path] [--odir path]
                   [--add AssignName NbName.ipynb]
                   [--fix AssignName NbName.ipynb]
                   [--meta AssignName NbName.ipynb]
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
  --cdir path           Override path to course_dir (default: current
                        directory)
  --sdir path           Override path to source directory
  --odir path           Override path to the submitted, autograded, or
                        feedback directory
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
  --sortcells AssignName NbName.ipynb
                        Sort cells of student notebooks to match order of
                        source, matches based on grade_id, non grade_id cells
                        are placed at the end
  --rmcells AssignName NbName.ipynb
                        MAKE SURE YOU BACKUP FIRST - Removes all student cells
                        that do not have a grade_id that matches the source
                        notebook (and sorts the ones that do) - this function
                        is destructive and should be used as a last resort
  --select StudentID [StudentID ...]
                        Select specific students to fix their notebooks
                        without having to run on the entire class (WARNING:
                        moves student(s) to <course_dir>/nbhelper-select-tmp
                        then moves back unless an error was encountered)
  --info AssignName     Get some quick info (student id, file size, cell
                        count, total execution count, [grade id : execution
                        count]) of all submissions and writes to
                        <course_dir>/reports/<AssignName>/info-<NbName>.csv
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
  --email AssignName|zip NbName.html|feedback.zip
                        Email feedback to students (see EMAIL_CONFIG in
                        script, prompts for unset fields)
  --ckdir AssignName NbName.extension
                        Check <course_dir>/feedback directory (change with
                        --odir) by printing studentIDs and matching files to
                        make sure it is structured properly
  --ckgrades AssignName
                        Checks for consistency between 'nbgrader export',
                        'dist', and 'fdist', and writes grades to
                        <course_dir>/reports/<AssignName>/grades-<NbName>.csv
  --ckdup NbName.extension
                        Checks all submitted directories for NbName.extension
                        and reports subfolders containing multiple files of
                        the same extension
  --chmod rwx AssignName
                        Run chmod rwx on all submissions for an assignment
                        (linux only)
  --zip AssignName [AssignName ...]
                        Combine multiple feedbacks into
                        <course_dir>/feedback/<student_id>/zip/feedback.zip
  --zipfiles NbName.html [NbName.html ...]
                        Same as zip but matches files instead of assignment
                        folders
  --backup nbgrader_step
                        Backup nbgrader_step directory to
                        <course_dir>/backups/<nbgrader_step-mm-dd-hh-mm>.zip
 ```
