#include <algorithm>
#include <iostream>
#include <fstream>
#include <chrono>
#include <thread>


bool cmdOptionExists(char** begin, char** end, const std::string& option)
{
    return std::find(begin, end, option) != end;
}

int getNumRunningProcess()
{
    int n = 0;
    std::string line;
    std::system("ps aux > .podman-hpc-ps");
    std::ifstream psfile(".podman-hpc-ps");

    while (std::getline(psfile, line))
        ++n;
    return n;
}


int main(int argc, char * argv[] )
{
  bool debug = cmdOptionExists(argv, argv+argc, "-d");

  int npid = getNumRunningProcess();
  if (debug) { std::cout << "ps aux returns " << npid << " lines" << std::endl; }

  while ( getNumRunningProcess() == npid ) 
  {
    if (debug) { std::cout << "waiting for additional processes to start" << std::endl; }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  while ( npid < getNumRunningProcess() )
  {
    if (debug) { std::cout << "waiting for additional processes to finish" << std::endl; }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  if (debug) { std::cout << "done" << std::endl; }

  std::cout << "Hello, World!" << std::endl;

  return 0;
}
