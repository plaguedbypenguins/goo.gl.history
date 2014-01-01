goo.gl.history
==============

Download and aggregate goo.gl statistics to track projects over time

this little tool gathers together statistics from an arbitrary number of goo.gl links, sums up the stats by "group", and then presents the stats in terms of (usually) downloads/week. a group is an arbitrary collection of goo.gl links, but is usually all the goo.gl links for one project, or all the links for each release of a project.

only unprivileged google APIs are used so this tool can be used to track goo.gl stats for anything.

configuration consists of listing the goo.gl links you want to watch in python dict format. eg. if you want to watch 'goo.gl/a00001' and 'goo.gl/a00002' for 'project a' and 'goo.gl/b00001' for 'project b' then your groups config would look like:

    groups = {'project a':['a00001', 'a00002'], 'project b':['b00001']}

the default config file name is 'goo.gl.history.conf.py'. this can be over-ridden by a command line argument eg. '-c /path/to/some_config_file.py'.
see '-h' for more options.

previously downloaded goo.gl stats are stored in pickle format in the file pointed to by 'dbName' (default: goo.gl.pickle).

country codes are expanded to country names using the list in 'countryName' (default: country.txt)
