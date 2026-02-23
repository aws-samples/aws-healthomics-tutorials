// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation

import com.amazon.vincent.job.models.AnnotationImportJobParameters
import org.junit.Assert.{assertEquals, assertFalse}
import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class FormatOptionsTests extends AnyFunSuite {

  test("Test empty vcf options return false") {
    val options = "{}"
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertFalse(vcfOptions.ignoreQualField.get)
    assertFalse(vcfOptions.ignoreFilterField.get)
  }

  test("test setting ignoreQualField") {
    val options = """{"vcfOptions": {"ignoreQualField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreQualField)
    assertEquals(vcfOptions.ignoreFilterField, None)
  }

  test("test setting ignoreFilterField") {
    val options = """{"vcfOptions": {"ignoreFilterField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreFilterField)
    assertEquals(vcfOptions.ignoreQualField, None)
  }

  test("setting both ignoreQualField and ignoreFilterField as true") {
    val options = """{"vcfOptions": {"ignoreFilterField": true, "ignoreQualField": true}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(true), vcfOptions.ignoreFilterField)
    assertEquals(Some(true), vcfOptions.ignoreQualField)
  }

  test("setting both vcfOptions as False") {
    val options = """{"vcfOptions": {"ignoreFilterField": false, "ignoreQualField": false}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(Some(false), vcfOptions.ignoreFilterField)
    assertEquals(Some(false), vcfOptions.ignoreQualField)
  }

  test("vcfOptions is an empty object") {
    val options = """{"vcfOptions": {}}"""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(vcfOptions.ignoreQualField, None)
    assertEquals(vcfOptions.ignoreFilterField, None)
  }

  test("vcfOptions is an empty string") {
    val options = ""
    val vcfOptions = AnnotationImportJobParameters.parseVCFOptions(options)
    assertEquals(vcfOptions.ignoreQualField, Some(false))
    assertEquals(vcfOptions.ignoreFilterField, Some(false))
  }
}
