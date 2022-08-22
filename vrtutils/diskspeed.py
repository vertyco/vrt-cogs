import os
import sys
from random import shuffle
from time import perf_counter as time


blocks_count = 256
block_size = 1048576


def get_write_speed(path):
    f = os.open(path, os.O_CREAT | os.O_WRONLY, 0o777)  # Low Level I/O
    w_times = []
    for i in range(blocks_count):
        sys.stdout.flush()
        buff = os.urandom(block_size)
        start = time()
        os.write(f, buff)
        os.fsync(f)
        w_times.append(time() - start)
    os.close(f)

    write_speed = blocks_count / sum(w_times)  # MB/s
    return write_speed


def get_read_speed(path):
    f = os.open(path, os.O_RDONLY, 0o777)
    # Generate Random Read Positions
    offsets = list(range(0, blocks_count * block_size, block_size))
    shuffle(offsets)

    r_times = []
    for i, offset in enumerate(offsets, 1):
        start = time()
        os.lseek(f, offset, os.SEEK_SET)  # Set Position
        buff = os.read(f, block_size)  # Read From Position
        t = time() - start
        if not buff:
            break  # If EOF Reached
        r_times.append(t)
    os.close(f)

    read_speed = blocks_count / sum(r_times)  # MB/s
    return read_speed


def get_disk_speed(path):
    path = os.path.join(path, "DiskSpeedTest")
    write = get_write_speed(path)
    read = get_read_speed(path)
    data = {
        "write": write,
        "read": read
    }
    os.remove(path)
    return data


if __name__ == "__main__":
    drive_name = "C:\\Users\\GAMER\\DiskSpeedTest"
    print(get_write_speed(drive_name))
    print(get_read_speed(drive_name))
