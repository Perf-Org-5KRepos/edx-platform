# rm -rf ~/.nvm && git clone https://github.com/creationix/nvm.git ~/.nvm && (cd ~/.nvm && git checkout `git describe --abbrev=0 --tags`) && . ~/.nvm/nvm.sh && nvm install 6.9.4
# sudo apt-get install npm -y
# npm install
# pip install setuptools
# pip install --exists-action w -r requirements/edx/paver.txt

# # Mirror what paver install_prereqs does.
# # After a successful build, Travis will
# # cache the virtualenv at that state, so that
# # the next build will not need to install them
# # from scratch again.
# pip install --exists-action w -r requirements/edx/pre.txt
# pip install --exists-action w -r requirements/edx/github.txt
# pip install --exists-action w -r requirements/edx/local.txt

# # HACK: within base.txt stevedore had a
# # dependency on a version range of pbr.
# # Install a version which falls within that range.
# pip install --exists-action w pbr==0.9.0
# pip install --exists-action w -r requirements/edx/base.txt
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 0C49F3730359A14518585931BC711F9BA15703C6
echo "deb [ arch=amd64,arm64 ] http://repo.mongodb.org/apt/ubuntu xenial/mongodb-org/3.4 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-3.4.list
sudo apt-get update -y
sudo apt-get install -y mongodb-org
# sudo apt-get install libxmlsec1-dev -y
# sudo apt-get install swig -y

# if [ -e requirements/edx/post.txt ]; then pip install --exists-action w -r requirements/edx/post.txt ; fi