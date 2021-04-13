.. title:: Accessibility statement for Numbas exams

Accessibility statement for Numbas exams
========================================

Numbas should be accessible to everyone who needs to or would like to use it.

Accessibility is an important consideration during the design and development process.
We regularly test Numbas against a variety of accessibility requirements.

This statement was prepared in October 2019.

What’s covered by this statement
--------------------------------

The Numbas runtime, as seen by students, using the default theme.

What’s not covered by this statement
------------------------------------

This statement does not cover the Numbas editor or Numbas LTI tool provider.

This statement does not cover the text content of questions written using Numbas - the question author is responsible for ensuring it's accessible.

Authors often embed content such as videos in Numbas questions.
Apart from these, the Numbas interface doesn’t include any videos or sound effects.

Numbas supports custom interface themes and extensions to provide new functionality.
Themes and extensions developed by the Numbas team are designed with the same accessibility considerations as the main Numbas system, but third-party themes and extensions are the responsibility of their authors.

Compliance with standards
-------------------------

We aim to meet `WCAG 2.1 <https://www.w3.org/TR/WCAG21/>`__ AA level standards.

Particular accessibility requirements we’ve designed around
-----------------------------------------------------------

-  Still usable when zoomed to 200%.
-  Colour is never used as the sole means of conveying information.
-  Ensure a colour contrast ratio of at least 7:1 (WCAG level AAA) throughout the interface.
-  The interface can be navigated entirely with the keyboard.
-  All content on the page is screen-readable, with sensible descriptions.
-  Very few animations; reduce motion as much as possible when browsers request it.
-  Layout is responsive and usable on screens with a variety of resolutions, including mobile devices.

Compatibility with browsers
---------------------------

We have tested Numbas on the following browsers.
Any more recent versions should be assumed to work.

-  Chrome version 10.
-  Firefox version 7.
-  Internet Explorer 9.
-  Edge any version.
-  Safari 5.0 on desktop.
-  iOS (iPhone/iPad) 8.0 with Safari.
-  Android 5.0 (Lollipop) with Chrome.

How to adapt Numbas to your needs
---------------------------------

Change the colours of text and the page background
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Click the :guilabel:`Display options` button to change the colour of text and the page's background.

Your browser's colour picker is used. 
In most browsers, you can pick a colour by clicking on a colour wheel, or by typing a colour value in hexadecimal or RGB format.


Changing the size of text
~~~~~~~~~~~~~~~~~~~~~~~~~

Use your browser’s zoom setting to change the size of text and interface elements.
This is often under ‘Zoom’ in the browser’s settings menu; you can also zoom in or out by pressing ``Ctrl +`` or ``Ctrl -`` on the keyboard (``Cmd +`` or ``Cmd -`` on Macs).
Mobile users can use a pinch gesture to zoom in and out.

Enlarging images
~~~~~~~~~~~~~~~~

You can click on an image to enlarge it to nearly fill the screen.
Click outside the image or press the Escape key to return to the main interface.

Navigating with a keyboard
~~~~~~~~~~~~~~~~~~~~~~~~~~

In most browsers, pressing the Tab key will move focus between interactive elements in the display.

Numbas uses the `MathJax accessibility extensions <http://docs.mathjax.org/en/latest/basic/a11y-extensions.html#interactive-exploration>`__ to provide interactive exploration of mathematical notation.

Printing a Numbas exam
~~~~~~~~~~~~~~~~~~~~~~

The default Numbas theme contains a print stylesheet which your browser can use to produce a printed version of an exam. 
After starting a Numbas exam, use your browser’s :guilabel:`Print` feature.

Using a screenreader
~~~~~~~~~~~~~~~~~~~~

A screenreader such as `NVDA <https://www.nvaccess.org/>`__, JAWS or Orca will read all of the content in a Numbas exam.
We’ve tested Numbas with NVDA and Orca.

When you submit an answer, the score and any feedback messages will be read out.

Mathematical notation is made accessible to a screenreader by the `MathJax accessibility extensions <http://docs.mathjax.org/en/latest/basic/a11y-extensions.html#speech-braille-support>`__.

Who to contact if you have problems or want to give feedback
------------------------------------------------------------

Students should contact their instructor, in the first instance.

Instructors and authors of Numbas content can contact us through any of the following:

-  Email numbas@ncl.ac.uk.
-  File an issue on `the Numbas GitHub repository <https://github.com/numbas/Numbas/issues>`__.
-  Post on `the numbas-users group <https://groups.google.com/forum/#!forum/numbas-users>`__.
