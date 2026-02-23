// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class TableFormatTest extends AnyFunSuite {

  test("test TableFormat suppported features") {
    assertResult(false)(TableFormat.supportsImportDataValidation(1))
    assertResult(true)(TableFormat.supportsImportDataValidation(2))
    assertResult(true)(TableFormat.supportsImportDataValidation(3))
    assertResult(false)(TableFormat.supportsVEPParsing(1))
    assertResult(false)(TableFormat.supportsVEPParsing(2))
    assertResult(true)(TableFormat.supportsVEPParsing(3))
  }

  test("Test TableFormat version and name") {
    assertResult(1)(TableFormat.version("hive_0"))
    assertResult(2)(TableFormat.version("iceberg_0"))
    assertResult(3)(TableFormat.version("iceberg_1"))
  }
}
