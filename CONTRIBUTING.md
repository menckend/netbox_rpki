# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## General Tips for Working on GitHub

* Register for a free [GitHub account](https://github.com/signup) if you haven't already.
* You can use [GitHub Markdown](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax) for formatting text and adding images.
* To help mitigate notification spam, please avoid "bumping" issues with no activity. (To vote an issue up or down, use a :thumbsup: or :thumbsdown: reaction.)
* Please avoid pinging members with `@` unless they've previously expressed interest or involvement with that particular issue.
* Familiarize yourself with [this list of discussion anti-patterns](https://github.com/bradfitz/issue-tracker-behaviors) and make every effort to avoid them.

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/menckend/netbox_rpki/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

NetBox RPKI Plugin could always use more documentation, whether as part of the
official NetBox RPKI Plugin docs, in docstrings, or even on the web in blog posts,
articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/menckend/netbox_rpki/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `netbox_rpki` for local development.

1. Fork the `netbox_rpki` repo on GitHub.
2. Clone your fork locally

    ```
    $ git clone git@github.com:your_name_here/netbox_rpki.git
    ```

3. Activate the NetBox virtual environment (see the NetBox documentation under [Setting up a Development Environment](https://docs.netbox.dev/en/stable/development/getting-started/)):

    ```
    $ source ~/.venv/netbox/bin/activate
    ```

4. Add the plugin to NetBox virtual environment in Develop mode (see [Plugins Development](https://docs.netbox.dev/en/stable/plugins/development/)):

    To ease development, install the plugin in editable mode from the plugin root directory:

    ```
    $ python -m pip install -e .
    ```

5. Create a branch for local development:

    ```
    $ git checkout -b name-of-your-bugfix-or-feature
    ```

    Now you can make your changes locally.

6. Commit your changes and push your branch to GitHub:

    ```
    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature
    ```

7. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work for Python 3.12, 3.13 and 3.14. Check
    https://github.com/menckend/netbox_rpki/actions
   and make sure that the tests pass for all supported Python versions.


## Deploying

A reminder for the maintainers on how to deploy.

Make sure all your changes are committed, the changelog is updated, and the docs build and test suite pass.

1. Push changes to `main` to publish the Sphinx documentation site to GitHub Pages.
2. Create and push a release tag such as `v0.1.6` to build the package, publish it to PyPI, sign the artifacts, and create the GitHub release.
3. Use the manual `Publish Release Artifacts` workflow with the `testpypi` target when you want a TestPyPI dry run before cutting a release tag.
