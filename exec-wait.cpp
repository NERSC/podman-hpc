#include <algorithm>
#include <iostream>
//#include <fstream>
#include <chrono>
#include <thread>
#include <unistd.h>
#include <limits.h>
//#include "boost/filesystem.hpp"
#include <filesystem>
#include <regex>

namespace fs = std::filesystem;

/**
 * Check for existence of command flags.
 *
 * @param begin Reference to the beginning of the argument buffer.
 * @param end Reference to the end of the argument buffer.
 * @param option The flag to search for.
 * @return boolean indicating whether the flag was found
 */
bool cmdOptionExists(char** begin, char** end, const std::string& option)
{
    return std::find(begin, end, option) != end;
}

/**
 * Return the result of a readlink call as a string.
 *
 * Attempts to read a link at the given path, and returns the character 
 * buffer as a std::string.  If there is an error reading the link,
 * returns an empty string.
 *
 * @param path String indicating path to a link to attempt to read.
 * @return String containing the value of the link.
 */
std::string readlink2str(std::string const& path) 
{
  char buf[PATH_MAX];
  ssize_t l = ::readlink(path.c_str(), buf, sizeof(buf)-1);
  if (l != -1)
  {
    buf[l] = '\0';
    return std::string(buf);
  }
  return std::string("");
}

/**
 * Count processes owned buy a user.
 *
 * Scans the /proc directory and checks for processes which have
 * an owner maching the supplied user string.  The user string 
 * should match the format of /proc/self/ns/user which typically
 * looks something like user:[1234567890].
 *
 * @param user String containing a user to match.
 * @result integer number of processes owned by user.
 */
int getNumRunningProcess(const std::string& user, const bool debug)
{
  std::string fn;
  int n = 0;

  for (fs::directory_iterator pitr("/proc"); pitr!=fs::directory_iterator(); ++pitr)
  {
    fn = pitr->path().filename();
    if (std::regex_match(fn, std::regex("[0-9]+")) && readlink2str("/proc/"+fn+"/ns/user") == user)
    { 
      n++;
    }
  }

  if (debug) { std::cout << "        getNumRunningProcess: detected " << n << " processes for user :" << user << std::endl; }
  return n;
}

/**
 * exec-wait
 *
 * This program will idle until the user has launched one or more 
 * additional processes, and then those processes have ended.  This 
 * is intended to be called by a container so that the main container
 * command does not exit until the users exec processes have all
 * exited.
 */
int main(int argc, char * argv[] )
{
  std::string user = readlink2str("/proc/self/ns/user");
  bool debug = cmdOptionExists(argv, argv+argc, "-d");
  int npid = getNumRunningProcess(user, debug);

  if (debug) { std::cout << "Detected " << npid << " running procs for " << user << "at launch." << std::endl; }

  while ( getNumRunningProcess(user, debug) == npid ) 
  {
    if (debug) { std::cout << "... waiting for additional processes to start" << std::endl; }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  while ( npid < getNumRunningProcess(user, debug) )
  {
    if (debug) { std::cout << "... waiting for additional processes to finish" << std::endl; }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  if (debug) { std::cout << "done" << std::endl; }

  return 0;
}
