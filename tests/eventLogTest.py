import win32evtlog
import os

server = 'localhost'
logtype = 'System'
hand = win32evtlog.OpenEventLog(server, logtype)
flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
total = win32evtlog.GetNumberOfEventLogRecords(hand)

print("Total number of Event record ", total)  #Returning 87399

save_path = 'C:/Users/GAMER/Documents'
filename = 'events'
completename = os.path.join(save_path, filename+".xml")
with open(completename, "a") as file:
    while True:
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        # print("Log record read", len(events))  # Returning 7
        for event in events:
            file.write(f"Event Category: {event.EventCategory}\n")
            file.write(f"Time Generated: {event.TimeGenerated}\n")
            file.write(f"Source Name: {event.SourceName}\n")
            file.write(f"Event ID: {event.EventID}\n")
            file.write(f"Event Type: {event.EventType}\n")
            file.write(f"Computer Name: {event.ComputerName}\n")
            file.write(f"Data Name: {event.Data}\n")
            data = event.StringInserts
            if data:
                print('Event Data:')
                file.write(f"Event Data:\n")
                for msg in data:
                    try:
                        file.write(f"{msg}\n")
                    except UnicodeError:
                        pass
                    print(msg)
            print('Event Category:', event.EventCategory)
            print('Time Generated:', event.TimeGenerated)
            print('Source Name:', event.SourceName)
            print('Event ID:', event.EventID)
            print('Event Type:', event.EventType)
            print('Computer Name:', event.ComputerName)
            print('Data Name:', event.Data)
            print(type(event))



