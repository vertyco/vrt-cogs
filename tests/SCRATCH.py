import win32evtlog
import os

server = 'localhost'
logtype = 'System'
hand = win32evtlog.OpenEventLog(server, logtype)
flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
total = win32evtlog.GetNumberOfEventLogRecords(hand)

print("Total number of Event record ", total)  #Returning 87399

# events = win32evtlog.ReadEventLog(hand, flags, 0)
# print("Log record read", len(events))  # Returning 7

n = 0
while n == 0:
    events = win32evtlog.ReadEventLog(hand, flags, 0)
    for event in events:
        data = event.StringInserts
        if data:
            for msg in data:
                if msg == "9NBLGGH52XC6-StudioWildcard.4558480580BB9":
                    if event.EventID == 44:
                        print("DOWNLOAD")
                    elif event.EventID == 43:
                        print("INSTALL")
                    elif event.EventID == 19:
                        print("INSTALL SUCCESS")
                    print('Time Generated:', event.TimeGenerated)
                    print('Source Name:', event.SourceName)
                    n = 1
                    # print('Event ID:', event.EventID)
                    # print('Event Type:', event.EventType)
                    # print('Computer Name:', event.ComputerName)
                    # print('Data Name:', event.Data)
                    # print(msg)




