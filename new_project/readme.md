mkdir new_project
cd new_project
echo "# new_project" > README.md
code .
git init
echo "# Http server" > index.html
python3 -m http.server