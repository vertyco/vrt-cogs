"""
Tests write/read speed by writing/reading random blocks.
Default Writes 128 Blocks of 1048576 bytes each i.e. 128MB
Arguments:
    path = Path of Drive to Test Speed
    blocks_count = Total quantity of blocks
    block_size = Side of each block (in bytes)

Found source code online and modified to use with VrtUtils
Original author is thodnev
https://github.com/thodnev/MonkeyTest
"""
import os
from random import shuffle
from time import perf_counter as time


def get_write_speed(path, blocks_count=128, block_size=1048576):
    f = os.open(path, os.O_CREAT | os.O_WRONLY, 0o777)  # Low Level I/O
    w_times = []
    for _ in range(blocks_count):
        buff = os.urandom(block_size)
        start = time()
        os.write(f, buff)
        os.fsync(f)
        w_times.append(time() - start)
    os.close(f)
    one_mb = 1048576
    ratio = (block_size / one_mb) if block_size >= one_mb else (one_mb / block_size)
    write_speed = blocks_count / (sum(w_times) * ratio)
    return write_speed  # MB/s


def get_read_speed(path, blocks_count=128, block_size=1048576):
    f = os.open(path, os.O_RDONLY, 0o777)
    # Generate Random Read Positions
    offsets = list(range(0, blocks_count * block_size, block_size))
    shuffle(offsets)

    r_times = []
    for offset in offsets:
        start = time()
        os.lseek(f, offset, os.SEEK_SET)  # Set Position
        buff = os.read(f, block_size)  # Read From Position
        t = time() - start
        if not buff:
            break  # If EOF Reached
        r_times.append(t)
    os.close(f)
    one_mb = 1048576
    ratio = (block_size / one_mb) if block_size >= one_mb else (one_mb / block_size)
    read_speed = blocks_count / (sum(r_times) * ratio)
    return read_speed  # MB/s


def get_disk_speed(path, blocks_count, block_size):
    path = os.path.join(path, "IOTest")
    write = get_write_speed(path, blocks_count, block_size)
    read = get_read_speed(path, blocks_count, block_size)
    data = {"write": write, "read": read}
    os.remove(path)
    return data


if __name__ == "__main__":
    maindir = os.getcwd()
    pathname = os.path.join(maindir, "IOTest")
    print(get_write_speed(pathname))
    print(get_read_speed(pathname))
    os.remove(pathname)
