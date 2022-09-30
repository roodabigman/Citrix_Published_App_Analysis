# citrix-monitor-reporting
programs for collecting custom reporting from the Monitor DB for Citrix DaaS sites

MONITOR COLLECTION EXE README
##############################################################
How to run:
1. Open Command Prompt window on your machine
2. click the cmd icon in the upper left of the cmd window, menu should drop down, click Properties
3. Under "Edit options" deselect "QuickEdit Mode" and "insert Mode"
4. click OK
5. Either drag-and-drop the EXE into the window, or cd to the exe directory and enter file name
6. hit enter to start the exe once the path is in the cmd window
7. go through the exe as normal


##############################################################
what's new:
version 0.7:
	- added new line before bearer token refresh output to prevent printing to progress bar line
	- included function for estimating time that takes throttling into account after the first ~100,000 sessions
	- change end time, if not specified, to be datetime.now() instead of ne null - to prevent the amount of sessions from increasing while the data is being collected
	- changed duration calculation to be [h]:mm:ss string output so that excel does not interpret as calendar dates
	- changed progress bar library to use tqdm.auto to draw bar more consistently in different windows

Version 0.6: 
	- Bearer token refresh logic for large data collection processes that take more than 1 hour to run (bearer tokens have 60 minute lifetimes)
	- new logic that allows selection of a new start date and end date if the amount of data to be collected based on enteres start / end is
	  larger than desired (version 0.5 would quit and force you to re-run the program)

version 0.5:
	- exception handling for cases where application details are null
	- enhanced console output when errors are encountered
	- retry mechanism for API calls, each call will now retry 4 times if needed, with a 2 second pause between each attempt
